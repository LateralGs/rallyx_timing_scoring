#!/usr/bin/python2
import logging
try:
  import tendo.colorer
except ImportError:
  print "no colorer"
logging.basicConfig(level=logging.DEBUG) # initialize this early so we get all output

from flask import *
from os import urandom
from util import *
from sql_db import ScoringDatabase
from time import time
import datetime

#######################################

# main wsgi app
app = Flask(__name__)

# load our config settings
app.config.from_pyfile('config.py')

# allows use of secure cookies for sessions
try:
  # load key from secret_key.py
  from secret_key import secret_key
  app.secret_key = secret_key
except:
  # default to random generated key
  app.secret_key = urandom(24)

# add some useful template filters
app.jinja_env.filters['format_time']=format_time
app.jinja_env.filters['pad']=pad


#######################################

# per appcontext database session
def get_db():
  db = getattr(g, '_database', None)
  if db is None:
    db = g._database = ScoringDatabase(app.config['SCORING_DB_PATH'])
  return db

@app.teardown_appcontext
def close_db(exception):
  db = getattr(g, '_database', None)
  if db is not None:
    db.close()

#######################################

@app.route('/')
def index_page():
  db = get_db()
  db.reg_inc('.pc_browser_index')

  g.active_event_id = db.reg_get_int('active_event_id')
  
  if g.active_event_id is None:
    return "No active event."

  g.active_event = db.event_get(g.active_event_id)
  g.max_runs = db.reg_get_int("max_runs", app.config['DEFAULT_MAX_RUNS'])

  # sort entries into car class
  g.class_entry_list = {}
  g.entry_driver_list = db.entry_driver_list(g.active_event_id)
  for entry in g.entry_driver_list:
    if entry['car_class'] not in g.class_entry_list:
      g.class_entry_list[entry['car_class']] = []
    if entry['show_scores']:
      g.class_entry_list[entry['car_class']].append(entry)

  # sort each car class by event_time_ms
  for car_class in g.class_entry_list:
    g.class_entry_list[car_class].sort(cmp=time_cmp, key=lambda e: e['event_time_ms'])

  g.entry_run_list = {}
  for entry in g.entry_driver_list:
    g.entry_run_list[entry['entry_id']] = db.run_list(entry_id=entry['entry_id'], state_filter=('scored',), limit=g.max_runs)

  return render_template('scoring_browser_index.html')

@app.route('/finish')
def finish_page():
  db = get_db()
  db.reg_inc('.pc_browser_finish')

  g.active_event_id = db.reg_get_int('active_event_id')

  if g.active_event_id is None:
    return "No active event."

  g.max_runs = db.reg_get_int("max_runs", app.config['DEFAULT_MAX_RUNS'])

  g.latest_runs = []
  for run in db.run_list(event_id=g.active_event_id, state_filter=('scored',), rev_sort=True, limit=10):
    run_info = {'car_class':None, 'first_name':None, 'last_name':None, 'alt_name':None, 'raw_time':None, 'cones':None, 'gates':None, 'total_time':None, 'run_count':None, 'car_number':None}
    entry = db.entry_driver_get(run['entry_id'])
    if entry is not None:
      run_info['car_class'] = entry['car_class']
      run_info['first_name'] = entry['first_name']
      run_info['last_name'] = entry['last_name']
      run_info['car_number'] = entry['car_number']
    run_info['raw_time'] = run['raw_time']
    run_info['cones'] = run['cones']
    run_info['gates'] = run['gates']
    run_info['total_time'] = run['total_time']
    run_info['run_count'] = run['run_count']
    logging.debug(run_info)
    g.latest_runs.append(run_info)

  return render_template('scoring_browser_finish.html')

#######################################

if __name__ == '__main__':
  # start dev server at localhost:8080
  app.run(host="0.0.0.0", port=8080, debug=True)


