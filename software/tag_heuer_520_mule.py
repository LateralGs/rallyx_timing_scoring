import logging
import uwsgi
import threading
from sql_db import ScoringDatabase
from time import sleep, time
import datetime
import scoring_rules

from tag_heuer_520 import TagHeuer520
from util import play_sound

try:
  import scoring_config as config
except ImportError:
  raise ImportError("Unable to load scoring_config.py, please reference install instructions!")

DB_POLL_INTERVAL = 3

DEFAULT_START_DEADTIME_INTERVAL = 10
DEFAULT_FINISH_DEADTIME_INTERVAL = 10
DEFAULT_SPLIT_1_DEADTIME_INTERVAL = 10
DEFAULT_SPLIT_2_DEADTIME_INTERVAL = 10

#######################################

def get_db():
  return ScoringDatabase(config.SCORING_DB_PATH)

def get_event(db):
  active_event_id = db.reg_get('active_event_id')
  if db.event_exists(active_event_id):
    return db.select_one('events', event_id=active_event_id)

def get_rules(event):
  if event is None:
    return None
  rule_sets = scoring_rules.get_rule_sets()
  if event['rule_set'] in rule_sets:
    rules = rule_sets[event['rule_set']]()
    if event['max_runs'] is not None:
      rules.max_runs = event['max_runs']
    if event['drop_runs'] is not None:
      rules.drop_runs = event['drop_runs']
    return rules
  else:
    return None

#######################################

def handle_start_event(db, event, rules, time_ms, time_id):
  next_entry_id = db.reg_get_int('next_entry_id')
  db.reg_set('next_entry_id', None)
  db.reg_set('next_entry_msg', None)
  disable_start = db.reg_get_int('disable_start', 0)

  if not disable_start:
    run_id = db.run_started(event['event_id'], time_ms, next_entry_id)
    if run_id is None:
      db.update('times', time_id, invalid=True)
      logging.info("Start [FALSE]: %r", time_id)
      play_sound('sounds/FalseStart.wav')
    else:
      db.set_run_recalc(run_id)
      uwsgi.mule_msg('recalc')
      logging.info("Start: %r", time_id)
      play_sound('sounds/CarStarted.wav')
  else:
    db.update('times', time_id, invalid=True)
    logging.info("Start [DISABLED]: %r", time_id)
    play_sound('sounds/FalseStart.wav')

def handle_finish_event(db, event, rules, time_ms, time_id):
  disable_finish = db.reg_get_int('disable_finish', 0)

  if not disable_finish:
    run_id = db.run_finished(event['event_id'], time_ms)
    if run_id is None:
      db.update('times', time_id, invalid=True)
      logging.info("Finish [FALSE]: %r", time_id)
      play_sound('sounds/FalseFinish.wav')
    else:
      db.set_run_recalc(run_id)
      uwsgi.mule_msg('recalc')
      logging.info("Finish: %r", time_id)
      play_sound('sounds/CarFinished.wav')
  else:
    db.update('times', time_id, invalid=True)
    logging.info("Finish [DISABLED]: %r", time_id)
    play_sound('sounds/FalseFinish.wav')

def handle_split_1_event(db, event, rules, time_ms, time_id):
  disable_split_1 = db.reg_get_int('disable_split_1', 0)
  # TODO
  logging.warning("SPLIT 1 not implemented")

def handle_split_2_event(db, event, rules, time_ms, time_id):
  disable_split_2 = db.reg_get_int('disable_split_2', 0)
  # TODO
  logging.warning("SPLIT 2 not implemented")

#######################################

def handle_time_event(db, channel, time_ms):
  event = get_event(db)
  rules = get_rules(event)

  if event is None:
    logging.error("invalid event")
    play_sound('sounds/FalseStart.wav')
    return
  if rules is None:
    logging.error("invalid event rule set")
    play_sound('sounds/FalseStart.wav')
    return

  time_id = db.insert('times', event_id=event["event_id"], channel=channel, time_ms=time_ms)

  if channel in ('1', 'M1', '01'): # start
    logging.info("start event")
    handle_start_event(db, event, rules, time_ms, time_id)
  elif channel in ('2', 'M2', '02'): # finish
    logging.info("finish event")
    handle_finish_event(db, event, rules, time_ms, time_id)
  elif channel in ('3', 'M3', '03'): # split 1
    logging.info("split_1 event")
    handle_split_1_event(db, event, rules, time_ms, time_id)
  elif channel in ('4', 'M4', '04'): # split 2
    logging.info("split_2 event")
    handle_split_2_event(db, event, rules, time_ms, time_id)
  else:
    logging.error("bad channel, %r", channel)


#######################################

if __name__ == '__main__':
  logging.warning("start tag heuer 520 mule")
  db = get_db()
  tag_heuer = TagHeuer520()
  open_state = True
  port = None
  
  poll_time = 0
  start_dead_time = 0
  finish_dead_time = 0
  split_1_dead_time = 0
  split_2_dead_time = 0

  while True:
    if poll_time < time():
      poll_time = time() + DB_POLL_INTERVAL
      port = db.reg_get('serial_port_tag_heuer')

    if tag_heuer.is_open() and tag_heuer.port != port:
      tag_heuer.close()
    elif tag_heuer.is_open():
      time_data = tag_heuer.read() # None or (channel, time_ms)
      if time_data is not None:
        channel, time_ms = time_data
        handle_time_event(db, channel, time_ms)
      else:
        sleep(0.1)
    elif port is not None and tag_heuer.open(port):
      db.reg_set('tag_heuer_status', 'open')
      logging.warning("tag_heuer_status: open")
      open_state = True
    elif open_state:
      db.reg_set('tag_heuer_status', 'closed')
      logging.warning("tag_heuer_status: closed")
      open_state = False
      sleep(1)
    else:
      sleep(1)

  


