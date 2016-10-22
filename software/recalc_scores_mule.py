import logging
import uwsgi
import threading
from sql_db import ScoringDatabase
from time import sleep, time
import datetime

from util import play_sound

try:
  import scoring_config as config
except ImportError:
  raise ImportError("Unable to load scoring_config.py, please reference install instructions!")

DB_POLL_INTERVAL = 3
RECALC_SIGNAL = 1

#######################################

def get_db():
  return ScoringDatabase(config.SCORING_DB_PATH)

def get_rules(db=None):
  rules = config.SCORING_RULES_CLASS()
  if db:
    rules.sync(db)
  return rules

#######################################

if __name__ == '__main__':
  logging.warning("start recalc scores mule")
  db = get_db()
  rules = get_rules(db)

  #uwsgi.add_timer(RECALC_SIGNAL, 3)

  while True:
    logging.debug("recalc waiting... id=%r", uwsgi.worker_id())
    uwsgi.mule_get_msg()
    logging.debug("RECALC")

    entry_id = 1 # trigger first iteration
    while entry_id is not None:
      # find next item to recalc
      with db:
        entry_id = db.query_single("SELECT entry_id FROM entries WHERE event_id=? AND recalc=1", (db.reg_get('active_event_id'),))
        if entry_id is not None:
          # reserve recalc
          db.update('entries', entry_id, recalc=2)
          rules.sync(db)
          rules.recalc_entry(db, entry_id)



  


