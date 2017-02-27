import logging
import uwsgi
import threading
from sql_db import ScoringDatabase
from time import sleep, time
import datetime
import scoring_rules

from util import play_sound

try:
  import scoring_config as config
except ImportError:
  raise ImportError("Unable to load scoring_config.py, please reference install instructions!")

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

if __name__ == '__main__':
  logging.warning("start recalc scores mule")
  db = get_db()

  while True:
    logging.debug("recalc waiting... mule_id=%r", uwsgi.mule_id())
    uwsgi.mule_get_msg() # wait on any msg indicating we need to recalc something
    # FIXME consider changing this to uwsgi.signal_wait() so that we can filter on a particular type
    logging.debug("RECALC")

    entry_id = 1 # trigger first iteration
    while entry_id is not None:
      # find next item to recalc
      with db:
        event = get_event(db)
        entry_id = db.query_single("SELECT entry_id FROM entries WHERE event_id=? AND recalc=1", (event['event_id'],))
        if entry_id is not None:
          # reserve recalc
          db.update('entries', entry_id, recalc=2)
          rules = get_rules(event)
          rules.recalc_entry(db, entry_id)



  


