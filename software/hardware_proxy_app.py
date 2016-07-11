#!/usr/bin/python2
import logging
try:
  import tendo.colorer
except ImportError:
  print "no colorer"
logging.basicConfig(level=logging.DEBUG) # initialize this early so we get all output

import threading
import config
from sql_db import ScoringDatabase
from Queue import Queue, Empty
from time import sleep, time
import datetime

# modules for interfacing to hardware
from tag_heuer_520 import TagHeuer520
from rallyx_timer import RallyXTimer
from barcode_scanner import BarcodeScanner, decode_license
from rfid_reader import RFIDReader
from util import play_sound

#######################################

event_queue = Queue()

debounce_ms = config.DEFAULT_DEBOUNCE_MS
deadtime_ms = config.DEFAULT_DEADTIME_MS
update_rallyx_timer = False

#######################################

def scanner_thread():
  log = logging.getLogger('scanner')
  scanner = BarcodeScanner()
  while True:
    if scanner.is_open():
      scanner_open = True
      scanner_data = scanner.read()
      if scanner_data is None:
        sleep(0.1)
      else:
        event_queue.put(('scanner_data', scanner_data))
    elif scanner.open(config.SERIAL_PORT_LICENSE_SCANNER):
      event_queue.put(('scanner_status', 'Open'))
    else:
      event_queue.put(('scanner_status', 'Closed'))
      sleep(1)

#######################################

def tag_heuer_thread():
  log = logging.getLogger('tag_heuer')
  open_state = True
  timer = TagHeuer520()
  while True:
    if timer.is_open():
      time_data = timer.read() # None or (channel, time_ms)
      if time_data is None:
        sleep(0.1)
      else:
        event_queue.put(('time_data', time_data))
    elif timer.open(config.SERIAL_PORT_TAG_HEUER_520):
      event_queue.put(('tag_heuer_status', 'Open'))
      open_state = True
    elif open_state:
      event_queue.put(('tag_heuer_status', 'Closed'))
      open_state = False
      sleep(1)
    else:
      sleep(1)

#######################################

def rfid_thread():
  log = logging.getLogger('rfid')
  rfid_reader = RFIDReader()
  open_state = True
  prev_data = None
  dup_reset = 0
  while True:
    if rfid_reader.is_open():
      new_data = rfid_reader.read()
      if new_data is None:
        sleep(0.1)
        if dup_reset > 0:
          dup_reset -= 1
        else:
          prev_data = None
      elif new_data != prev_data:
        dup_reset = 2
        prev_data = new_data
        event_queue.put(('rfid_data', new_data))
        rfid_reader.beep()
        for i in range(3):
          rfid_reader.led_off()
          sleep(0.1)
          rfid_reader.led_on()
          sleep(0.1)
    elif rfid_reader.open(config.SERIAL_PORT_RFID_READER):
      event_queue.put(('rfid_status','Open'))
      rfid_reader.led_on()
      open_state = True
    elif open_state:
      event_queue.put(('rfid_status','Closed'))
      open_state = False
      sleep(1)
    else:
      sleep(1)

def watchdog_thread():
  timeout_msg = True
  log = logging.getLogger('watchdog')

  while True:
    scanner_watchdog = False
    rallyx_timer_watchdog = False
    tag_heuer_watchdog = False
    rfid_watchdog = False
    active_threads = threading.enumerate()
    for t in active_threads:
      if t.name == 'scanner':
        scanner_watchdog = True
      elif t.name == 'tag_heuer':
        tag_heuer_watchdog = True
      elif t.name == 'rfid':
        rfid_watchdog = True
    if scanner_watchdog and tag_heuer_watchdog and rfid_watchdog:
      event_queue.put(('watchdog', time()))
      timeout_msg = True
    elif timeout_msg:
      log.error("WATCHDOG TIMEOUT")
      timeout_msg = False
    sleep(1)

if __name__ == '__main__':
  # if available only allow a single instance of this script to run
  try:
    import tendo.singleton
  except ImportError:
    pass
  else:
    me = tendo.singleton.SingleInstance()
    logging.getLogger("singleton").debug(me)

  # start threads for talking to hardware
  scanner_thread_obj = threading.Thread(target=scanner_thread, name="scanner")
  tag_heuer_thread_obj = threading.Thread(target=tag_heuer_thread, name="tag_heuer")
  rfid_thread_obj = threading.Thread(target=rfid_thread, name="rfid")
  watchdog_thread_obj = threading.Thread(target=watchdog_thread, name="watchdog")

  scanner_thread_obj.daemon = True
  tag_heuer_thread_obj.daemon = True
  rfid_thread_obj.daemon = True
  watchdog_thread_obj.daemon = True

  scanner_thread_obj.start()
  tag_heuer_thread_obj.start()
  rfid_thread_obj.start()
  watchdog_thread_obj.start()

  log = logging.getLogger('main')

  with ScoringDatabase(config.SCORING_DB_PATH) as db:
    db.reg_set_default('debounce_ms', config.DEFAULT_DEBOUNCE_MS)
    db.reg_set_default('deadtime_ms', config.DEFAULT_DEADTIME_MS)
    while True:
      try:
        evt_type, evt_data = event_queue.get(True, 1) # blocking, 1 sec timeout
      except Empty:
        # handle idle stuff
        new_debounce_ms = db.reg_get_int('debounce_ms', config.DEFAULT_DEBOUNCE_MS)
        new_deadtime_ms = db.reg_get_int('deadtime_ms', config.DEFAULT_DEADTIME_MS)
        if new_debounce_ms != debounce_ms or new_deadtime_ms != deadtime_ms:
          debounce_ms = new_debounce_ms
          deadtime_ms = new_deadtime_ms
          update_rallyx_timer = True
        continue
      log.info("%r, %r", evt_type, evt_data)
      if evt_type == 'scanner_data':
        scan_id, scan_data = evt_data
        if scan_id == 'j':
          license_data = decode_pdf417(scan_data)
          db.reg_set('scanner_license_data', license_data)
        else:
          db.reg_set('scanner_data', scan_data)
      elif evt_type == 'time_data':
        active_event_id = db.reg_get_int('active_event_id')

        if active_event_id is None:
          log.warning("active_event_id is None")
          if evt_data[0] in ('1','M1'):
            play_sound("sounds/FalseStart.wav")
          else:
            play_sound("sounds/FalseFinish.wav")

        elif evt_data[0] in ('1','M1'):
          next_entry_id = db.reg_get_int('next_entry_id')
          db.reg_set('next_entry_id', None)
          disable_start = db.reg_get_int('disable_start', 0)
          time_id = db.time_insert(active_event_id, evt_data[0], evt_data[1], disable_start)

          if not disable_start:
            run_id = db.run_started(active_event_id, evt_data[1], next_entry_id)
            if run_id is None:
              db.time_update(time_id, invalid=True)
              log.info("Start [FALSE]: %r", evt_data)
              play_sound("sounds/FalseStart.wav")
            else:
              db.run_recalc(run_id, config.CONE_PENALTY, config.GATE_PENALTY)
              log.info("Start: %r", evt_data)
              play_sound("sounds/CarStarted.wav")
          else:
            log.info("Start [DISABLED]: %r", evt_data)
            play_sound("sounds/FalseStart.wav")

        elif evt_data[0] in ('2','M2'):
          disable_finish = db.reg_get_int('disable_finish', 0)
          time_id = db.time_insert(active_event_id, evt_data[0], evt_data[1], disable_finish)

          if not disable_finish:
            run_id = db.run_finished(active_event_id, evt_data[1])
            if run_id is None:
              db.time_update(time_id, invalid=True)
              log.info("Finish [FALSE]: %r", evt_data)
              play_sound("sounds/FalseFinish.wav")
            else:
              db.run_recalc(run_id, config.CONE_PENALTY, config.GATE_PENALTY)
              log.info("Finish: %r", evt_data)
              play_sound("sounds/CarFinished.wav")
          else:
            log.info("Finish [DISABLED]: %r", evt_data)
            play_sound("sounds/FalseFinish.wav")
        else:
          log.warning("bad time channel, %r", evt_data[0])
      elif evt_type == 'rfid_data':
        db.reg_set('rfid_data', evt_data)
        try:
          rfid_number = int(evt_data)
        except ValueError:
          log.warning("Invalid rfid number")
          play_sound("sounds/OutputFailure.wav")
        else:
          entry = db.entry_by_rfid(db.reg_get('active_event_id'), rfid_number)
          if entry is None:
            log.warning("No entry_id found")
            play_sound("sounds/OutputFailure.wav")
          else:
            db.reg_set("next_entry_id", entry['entry_id'])
            log.info("Set next_entry_id, %r", entry['entry_id'])
            play_sound("sounds/OutputComplete.wav")
      elif evt_type == 'rfid_status':
        db.reg_set('rfid_status',evt_data)
      elif evt_type == 'tag_heuer_status':
        db.reg_set('tag_heuer_status', evt_data)
      elif evt_type == 'scanner_status':
        db.reg_set('scanner_status', evt_data)
      elif evt_type == 'watchdog':
        db.reg_set('hardware_watchdog', evt_data)
      else:
        log.warning('invalid event type, %r', evt_type)

  log.info("exiting...")

