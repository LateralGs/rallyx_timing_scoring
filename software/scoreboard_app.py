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

try:
  import markdown
except ImportError:
  app.logger.warning("Unable to import markdown module")
else:
  app.jinja_env.filters['markdown']=markdown.markdown

# remove extra whitespace from jinja output
app.jinja_env.trim_blocks=True
app.jinja_env.lstrip_blocks=True


#######################################

# per appcontext database session
def get_db():
  db = getattr(g, '_database', None)
  if db is None:
    db = g._database = ScoringDatabase(app.config['SCORING_DB_PATH'])
  return db

def get_rules(db):
  rules = getattr(g, '_rules', None)
  if rules is None:
    rules = g._rules = app.config['SCORING_RULES_CLASS']()
  rules.sync(db)
  return rules

@app.teardown_appcontext
def close_db(exception):
  db = getattr(g, '_database', None)
  if db is not None:
    db.close()

#######################################

@app.route('/')
def index_page():
  db = get_db()
  g.rules = get_rules(db)
  
  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    return "No active event."

  g.auto_refresh = request.args.get('auto_refresh')

  g.driver_entry_list = db.driver_entry_list(g.active_event_id)

  g.class_entry_list = {}
  g.driver_entry_list = db.driver_entry_list(g.active_event_id)
  for entry in g.driver_entry_list:
    if entry['car_class'] not in g.class_entry_list:
      g.class_entry_list[entry['car_class']] = []
    if entry['scores_visible']:
      g.class_entry_list[entry['car_class']].append(entry)

  # sort each car class by event_time_ms and run_count
  for car_class in g.class_entry_list:
    g.class_entry_list[car_class].sort(cmp=entry_cmp)

  g.entry_run_list = {}
  for entry in g.entry_driver_list:
    g.entry_run_list[entry['entry_id']] = db.run_list(entry_id=entry['entry_id'], state_filter=('scored',), limit=g.rules.max_runs, sort='A')

  return render_template('scoreboard_index.html')


@app.route('/finish')
def finish_page():
  db = get_db()
  g.rules = get_rules(db)
  
  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    return "No active event."

  g.auto_refresh = request.args.get('auto_refresh')

  g.driver_entry_list = db.driver_entry_list(g.active_event_id)

  g.driver_entry_dict = { entry['entry_id'] : entry for entry in g.driver_entry_list }

  g.latest_runs = db.run_list(event_id=g.active_event_id, state="scored", limit=10, sort='D')

  return render_template('scoreboard_finish.html')


@app.route('/sectors')
def sectors_page():
  db = get_db()
  g.rules = get_rule(db)
  g.active_event_id = db.reg_get_int('active_event_id')

  if g.active_event_id is None:
    return "No active event."

  return render_template('scoreboard_sectors.html')


@app.route('/penalties')
def penalties_page():
  db = get_db()
  g.rules = get_rule(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    return "No active event."

  g.auto_refresh = request.args.get('auto_refresh')

  g.driver_entry_list = db.driver_entry_list(g.active_event_id)

  g.driver_entry_dict = { entry['entry_id'] : entry for entry in g.driver_entry_list }

  g.penalty_list = db.select_all('penalties', event_id=g.active_event_id)

  return render_template('scoreboard_penalties.html')


#######################################

if __name__ == '__main__':
  # start dev server at localhost:8080
  app.run(host="0.0.0.0", port=8080, debug=True)


