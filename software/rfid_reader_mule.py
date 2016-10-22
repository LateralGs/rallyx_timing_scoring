
import logging
import uwsgi
import threading
from sql_db import ScoringDatabase
from time import sleep, time
import datetime

from rfid_reader import RFIDReader
from util import play_sound

try:
  import scoring_config as config
except ImportError:
  raise ImportError("Unable to load scoring_config.py, please reference install instructions!")

DB_POLL_INTERVAL = 3
REPEAT_INTERVAL = 3

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
    logging.warning("Invalid card number")
    play_sound('sounds/OutputFailure.wav')
    return

  race_session = db.reg_get('race_session')
  active_event_id = db.reg_get('active_event_id')
  entry_list = db.query_all("SELECT entry_id, race_session FROM driver_entries WHERE event_id=? AND card_number=?", (active_event_id, card_number))
  next_entry_id = None

  if entry_list is None or len(entry_list) == 0:
    logging.warning("No entry_id found")
  else:
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
    logging.warning("No entry for current session found")
    db.reg_set("next_entry_id", None)
    db.reg_set("next_entry_msg", "Invalid card_number or wrong session!")
    play_sound('sounds/OutputFailure.wav')
    return False
  else:
    db.reg_set("next_entry_id", next_entry_id)
    db.reg_set("next_entry_msg", None)
    logging.info("Set next_entry_id, %r", next_entry_id)
    play_sound('sounds/OutputComplete.wav')
    return True

#######################################

if __name__ == '__main__':
  logging.warning("start rfid reader mule")
  db = get_db()
  rfid_reader = RFIDReader()
  open_state = True
  prev_data = None
  port = None
  
  poll_time = 0
  repeat_time = 0
  while True:
    if poll_time < time():
      poll_time = time() + DB_POLL_INTERVAL
      port = db.reg_get('serial_port_rfid_reader')

    if rfid_reader.is_open() and rfid_reader.port != port:
      rfid_reader.close()
    elif rfid_reader.is_open():
      rfid_data = rfid_reader.read()
      if rfid_data is not None:
        rfid_reader.send_ack()
        rfid_reader.pause()
        if rfid_data != prev_data or repeat_time < time():
          prev_data = rfid_data
          repeat_time = time() + REPEAT_INTERVAL
          if handle_next_entry(db, rfid_data):
            rfid_reader.beep(2)
          else:
            rfid_reader.beep(5)
      else:
        sleep(0.1)
    elif port is not None and rfid_reader.open(port):
      db.reg_set('rfid_reader_status', 'open')
      logging.warning("rfid_reader_status: open")
      open_state = True
    elif open_state:
      db.reg_set('rfid_reader_status', 'closed')
      logging.warning("rfid_reader_status: closed")
      open_state = False
      sleep(1)
    else:
      sleep(1)

  

