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
from barcode_scanner import BarcodeScanner, decode_license
from rfid_reader import RFIDReader
from util import play_sound

#######################################

def get_db():
  return ScoringDatabase(config.SCORING_DB_PATH)

def get_rules(db=None):
  rules = config.SCORING_RULES_CLASS()
  if db:
    rules.sync(db)
  return rules

#######################################

def handle_next_entry(db, data):
  try:
    card_number = int(data)
  except ValueError:
    log.warning("Invalid card number")
    play_sound(config.SOUND_BAD_SCAN)
    return

  race_session = db.reg_get('race_session')
  active_event_id = db.reg_get('active_event_id')
  entry_list = list(db.cursor().execute("SELECT entry_id, race_session FROM entries WHERE event_id=? AND card_number=?", (active_event_id, card_number)))

  if entry_list is None or len(entry_list) == 0:
    log.warning("No entry_id found")
    play_sound(config.SOUND_BAD_SCAN)
  else:
    next_entry_id = None

    # search for an entry matching the current session
    for entry in entry_list:
      if entry['race_session'] == race_session:
        next_entry_id = entry['entry_id']
        break

    if next_entry_id == None:
      # search for an entry matching any session
      for entry in entry_list:
        if entry['race_session'] in ('-1', None,'*'):
          next_entry_id = entry['entry_id']
          break
    
    if next_entry_id is None:
      log.warning("No entry for current session found")
      db.reg_set("next_entry_id", None)
      db.reg_set("next_entry_msg", "Wrong Session!")
    else:
      db.reg_set("next_entry_id", next_entry_id)
      db.reg_set("next_entry_msg", None)
      log.info("Set next_entry_id, %r", next_entry_id)
      if db.reg_get_int('special_scan_id') == next_entry_id:
        play_sound(config.SOUND_GOOD_SCAN)
        sleep(0.5)
        play_sound("sounds/need_for_speed.mp3") # FIXME EASTER EGG
      else:
        play_sound(config.SOUND_GOOD_SCAN)

#######################################

# FIXME change all threads to poll for changes and handle db updates locally

def handle_barcode(db, data):
  if data.startswith("@"):
    license_data = decode_pdf417(data)
    db.reg_set('license_data', license_data)
  else:
    db.reg_set('barcode_data', data)
    handle_next_entry(db, data)

def barcode_scanner_thread():
  log = logging.getLogger('barcode_scanner')
  open_state = True
  scanner = BarcodeScanner()
  db = get_db()
  poll_time = time() + 3
  while True:
    if poll_time < time():
      poll_time = time() + 3
      port = db.reg_get('serial_port_barcode')

    if scanner.is_open() and scanner.port != port:
      scanner.close()
    elif scanner.is_open():
      barcode_data = scanner.read()
      if barcode_data is not None:
        handle_barcode(db, barcode_data)
      else:
        sleep(0.1)
    elif port is not None and scanner.open(port):
      db.reg_set('barcode_scanner_status', 'Open')
      open_state = True
    elif open_state:
      db.reg_set('barcode_scanner_status', 'Closed')
      open_state = False
      sleep(1)
    else:
      sleep(1)

#######################################

def rfid_reader_thread():
  log = logging.getLogger('rfid_reader')
  rfid_reader = RFIDReader()
  open_state = True
  prev_data = None
  port = None
  dup_reset = 0
  while True:
    if rfid_reader.is_open():
      new_data = rfid_reader.read()
      if new_data is None:
        if rfid_serial_port != port:
          rfid_reader.close()
        else:
          sleep(0.1)
          if dup_reset > 0:
            dup_reset -= 1
          else:
            prev_data = None
      else:
        if new_data != prev_data:
          dup_reset = 2
          prev_data = new_data
          event_queue.put(('rfid_data', new_data))
        rfid_reader.send_ack()
        rfid_reader.pause()
        rfid_reader.beep(2)
    elif rfid_reader.open(rfid_serial_port):
      port = rfid_reader.port
      event_queue.put(('rfid_status','Open'))
      open_state = True
    elif open_state:
      event_queue.put(('rfid_status','Closed'))
      open_state = False
      sleep(1)
    else:
      sleep(1)

#######################################

def handle_time_data(db, data):
  pass

def tag_heuer_thread():
  log = logging.getLogger('tag_heuer')
  open_state = True
  port = None
  tag_heuer = TagHeuer520()
  while True:
    if tag_heuer.is_open():
      time_data = tag_heuer.read() # None or (channel, time_ms)
      if time_data is None:
        if tag_heuer_serial_port != port:
          tag_heuer.close()
        else:
          sleep(0.1)
      else:
        event_queue.put(('time_data', time_data))
    elif tag_heuer.open(tag_heuer_serial_port):
      port = tag_heuer.port
      event_queue.put(('tag_heuer_status', 'Open'))
      open_state = True
    elif open_state:
      event_queue.put(('tag_heuer_status', 'Closed'))
      open_state = False
      sleep(1)
    else:
      sleep(1)

#######################################

def recalc_thread():
  log = logging.getLogger('recalc')
  poll_time = time() + 2
  while True:
    if poll_time < time():
      poll_time = time() + 2

      # TODO
      # check for entries with recalc flag
    else:
      sleep(1)

    

#######################################

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
  barcode_scanner_thread_obj = threading.Thread(target=barcode_scanner_thread, name="barcode_scanner")
  tag_heuer_thread_obj = threading.Thread(target=tag_heuer_thread, name="tag_heuer")
  rfid_reader_thread_obj = threading.Thread(target=rfid_reader_thread, name="rfid_reader")
  recalc_thread_obj = threading.Thread(target=recalc_thread, name="recalc")

  # allow all threads to be killed when main exits
  barcode_scanner_thread_obj.daemon = True
  tag_heuer_thread_obj.daemon = True
  rfid_reader_thread_obj.daemon = True
  recalc_thread_obj.daemon = True

  barcode_scanner_thread_obj.start()
  tag_heuer_thread_obj.start()
  rfid_reader_thread_obj.start()
  recalc_thread_obj.start()

  # monitor worker threads so we know if one fails
  timeout_msg = True
  wd_db = get_db()
  try:
    while True:
      if barcode_scanner_thread_obj.is_alive() and
          tag_heuer_thread_obj.is_alive() and
          rfid_reader_thread_obj.is_alive():
        wd_db.reg_set('worker_threads_watchdog', time())
        timeout_msg = True
      elif timeout_msg:
        log.error("WATCHDOG TIMEOUT")
        timeout_msg = False
      # watchdog interval
      sleep(3)
  except KeyboardInterrupt:
    log.info("exiting...")
    # TODO add any cleanup code here


#    while True:
#      # periodic polling stuff
#      if next_poll < time():
#        next_poll = time() + 3.0
#        rfid_serial_port = db.reg_get('serial_port_rfid')
#        barcode_serial_port = db.reg_get('serial_port_barcode')
#        tag_heuer_serial_port = db.reg_get('serial_port_tag_heuer')
#
#      try:
#        evt_type, evt_data = event_queue.get(True, 1) # blocking, 1 sec timeout
#      except Empty:
#        continue
#
#      log.info("%r, %r", evt_type, evt_data)
#
#      if evt_type == 'time_data':
#        active_event_id = db.reg_get_int('active_event_id')
#        rules.sync(db)
#
#        if active_event_id is None:
#          log.warning("active_event_id is None")
#          play_sound(config.SOUND_FALSE_START)
#
#        elif evt_data[0] in ('1','M1','01'):
#          next_entry_id = db.reg_get_int('next_entry_id')
#          db.reg_set('next_entry_id', None)
#          db.reg_set('next_entry_msg', None)
#          disable_start = db.reg_get_int('disable_start', 0)
#          time_id = db.time_insert(active_event_id, evt_data[0], evt_data[1], disable_start)
#          
#          if next_entry_id is not None and db.reg_get_int('special_start_id') == next_entry_id:
#            log.debug("%r == %r",db.reg_get_int('indy_start_id'), next_entry_id)
#            play_sound("sounds/Indiana_Jones_Theme.mp3") # FIXME EASTER EGG
#
#          if not disable_start:
#            run_id = db.run_started(active_event_id, evt_data[1], next_entry_id)
#            if run_id is None:
#              db.time_update(time_id, invalid=True)
#              log.info("Start [FALSE]: %r", evt_data)
#              play_sound(config.SOUND_FALSE_START)
#            else:
#              rules.run_recalc(db, run_id)
#              log.info("Start: %r", evt_data)
#              play_sound(config.SOUND_START)
#          else:
#            log.info("Start [DISABLED]: %r", evt_data)
#            play_sound(config.SOUND_FALSE_START)
#
#        elif evt_data[0] in ('2','M2','02'):
#          disable_finish = db.reg_get_int('disable_finish', 0)
#          time_id = db.time_insert(active_event_id, evt_data[0], evt_data[1], disable_finish)
#
#          if not disable_finish:
#            run_id = db.run_finished(active_event_id, evt_data[1])
#            if run_id is None:
#              db.time_update(time_id, invalid=True)
#              log.info("Finish [FALSE]: %r", evt_data)
#              play_sound(config.SOUND_FALSE_FINISH)
#            else:
#              rules.run_recalc(db, run_id)
#              log.info("Finish: %r", evt_data)
#              play_sound(config.SOUND_FINISH)
#          else:
#            log.info("Finish [DISABLED]: %r", evt_data)
#            play_sound(config.SOUND_FALSE_FINISH)
#
#        elif evt_data[0] in ('3', 'M3', '03'):
#          time_id = db.time_insert(active_event_id, evt_data[0], evt_data[1])
#          # FIXME add split 1 handling
#
#        elif evt_data[0] in ('4', 'M4', '04'):
#          time_id = db.time_insert(active_event_id, evt_data[0], evt_data[1])
#          # FIXME add split 2 handling
#
#        else:
#          log.warning("bad time channel, %r", evt_data[0])
#
#      elif evt_type == 'barcode_data':
#        if evt_data.startswith("@"):
#          license_data = decode_pdf417(evt_data)
#          db.reg_set('license_data', license_data)
#        else:
#          db.reg_set('barcode_data', evt_data)
#          try:
#            barcode_number = int(evt_data)
#          except ValueError:
#            log.warning("Invalid barcode number")
#            play_sound("sounds/OutputFailure.wav")
#          else:
#            race_session = db.reg_get('race_session')
#            entry_list = db.entries_by_card(db.reg_get('active_event_id'), barcode_number)
#            if entry_list is None or len(entry_list) == 0:
#              log.warning("No entry_id found")
#              play_sound(config.SOUND_BARCODE_SCAN_BAD)
#            else:
#              next_entry_id = None
#
#              # search for an entry matching the current session
#              for entry in entry_list:
#                if entry['race_session'] == race_session:
#                  next_entry_id = entry['entry_id']
#                  break
#
#              if next_entry_id == None:
#                # search for an entry matching any session (-1)
#                for entry in entry_list:
#                  if entry['race_session'] in ('-1', None):
#                    next_entry_id = entry['entry_id']
#                    break
#              
#              if next_entry_id is None:
#                log.warning("No entry for current session found")
#                db.reg_set("next_entry_id", None)
#                db.reg_set("next_entry_msg", "Wrong Session!")
#              else:
#                db.reg_set("next_entry_id", next_entry_id)
#                db.reg_set("next_entry_msg", None)
#                log.info("Set next_entry_id, %r", next_entry_id)
#                play_sound(config.SOUND_BARCODE_SCAN_GOOD)
#
#      elif evt_type == 'rfid_data':
#        db.reg_set('rfid_data', evt_data)
#        try:
#          rfid_number = int(evt_data)
#        except ValueError:
#          log.warning("Invalid rfid number")
#          play_sound("sounds/OutputFailure.wav")
#        else:
#          race_session = db.reg_get('race_session')
#          entry_list = db.entries_by_card(db.reg_get('active_event_id'), rfid_number)
#          if entry_list is None or len(entry_list) == 0:
#            log.warning("No entry_id found")
#            play_sound(config.SOUND_RFID_SCAN_BAD)
#          else:
#            next_entry_id = None
#
#            # search for an entry matching the current session
#            for entry in entry_list:
#              if entry['race_session'] == race_session:
#                next_entry_id = entry['entry_id']
#                break
#
#            if next_entry_id == None:
#              # search for an entry matching any session
#              for entry in entry_list:
#                if entry['race_session'] in ('-1', None):
#                  next_entry_id = entry['entry_id']
#                  break
#            
#            if next_entry_id is None:
#              log.warning("No entry for current session found")
#              db.reg_set("next_entry_id", None)
#              db.reg_set("next_entry_msg", "Wrong Session!")
#            else:
#              db.reg_set("next_entry_id", next_entry_id)
#              db.reg_set("next_entry_msg", None)
#              log.info("Set next_entry_id, %r", next_entry_id)
#              if db.reg_get_int('special_scan_id') == next_entry_id:
#                play_sound(config.SOUND_RFID_SCAN_GOOD)
#                sleep(0.5)
#                play_sound("sounds/need_for_speed.mp3") # FIXME EASTER EGG
#              else:
#                play_sound(config.SOUND_RFID_SCAN_GOOD)
#
#      
#      elif evt_type == 'rfid_status':
#        db.reg_set('rfid_status',evt_data)
#
#      elif evt_type == 'tag_heuer_status':
#        db.reg_set('tag_heuer_status', evt_data)
#
#      elif evt_type == 'barcode_scanner_status':
#        db.reg_set('barcode_scanner_status', evt_data)
#
#      elif evt_type == 'watchdog':
#        db.reg_set('hardware_watchdog', evt_data)
#
#      else:
#        log.warning('invalid event type, %r', evt_type)

  log.info("exiting...")

