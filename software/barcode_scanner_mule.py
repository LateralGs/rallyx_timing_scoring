import logging
import uwsgi
import threading
from sql_db import ScoringDatabase
from time import sleep, time
import datetime

from barcode_scanner import BarcodeScanner, decode_license
from util import play_sound

try:
  import scoring_config as config
except ImportError:
  raise ImportError("Unable to load scoring_config.py, please reference install instructions!")

DB_POLL_INTERVAL = 3

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
    play_sound('sounds/OutputFailure.wav')
    return

  race_session = db.reg_get('race_session')
  active_event_id = db.reg_get('active_event_id')
  entry_list = db.query_all("SELECT entry_id, race_session FROM entries WHERE event_id=? AND card_number=?", (active_event_id, card_number))

  if entry_list is None or len(entry_list) == 0:
    log.warning("No entry_id found")
    play_sound('sounds/OutputFailure.wav')
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
      play_sound('sounds/OutputComplete.wav')

#######################################

def handle_barcode(db, data):
  if data.startswith("@"):
    license_data = decode_pdf417(data)
    db.reg_set('license_data', license_data)
  else:
    db.reg_set('barcode_data', data)
    handle_next_entry(db, data)

#######################################

if __name__ == '__main__':
  logging.warning("start barcode scanner mule")
  db = get_db()
  log = logging.getLogger('barcode_scanner_mule')
  scanner = BarcodeScanner()
  open_state = True
  port = None
  
  poll_time = 0
  while True:
    if poll_time < time():
      poll_time = time() + DB_POLL_INTERVAL
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
      db.reg_set('barcode_scanner_status', 'open')
      open_state = True
    elif open_state:
      db.reg_set('barcode_scanner_status', 'closed')
      open_state = False
      sleep(1)
    else:
      sleep(1)

  


