#!/usr/bin/python2
import logging
try:
  import tendo.colorer
except ImportError:
  print "no colorer"
logging.basicConfig(level=logging.DEBUG) # initialize this early so we get all output

import sys

min_runs = int(sys.argv[1])
max_runs = int(sys.argv[2])
drop_runs = int(sys.argv[3])

import config
from sql_db import ScoringDatabase

with ScoringDatabase(config.SCORING_DB_PATH) as db:
  active_event_id = db.reg_get_int("active_event_id")
  if active_event_id is None:
    logging.error("No active event set!")
    sys.exit(1)

  entry_list = db.entry_list(active_event_id)
  for entry in entry_list:
    logging.info(entry['entry_id'])
    db.entry_recalc(entry['entry_id'],min_runs, max_runs, drop_runs)

  
  

