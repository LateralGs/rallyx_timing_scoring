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
import scoring_rules
from time import time, sleep
import datetime
import csv
from cStringIO import StringIO
from serial.tools.list_ports import comports
from glob import glob
import markdown

import uwsgidecorators
import uwsgi

import uuid
import random

#######################################
# message flash categories
F_ERROR = 'error'
F_WARN = 'warning'

# uwsgi signal for triggering recalc mule
RECALC_SIGNAL = 1

# main wsgi app
app = Flask(__name__)

# load our config settings for flask
app.config.from_pyfile('flask_config.py')

try:
  import scoring_config as config
except ImportError:
  raise ImportError("Unable to load scoring_config.py, please reference install instructions!")

# this will implicitly test the db schema and init if needed
test_db = ScoringDatabase(config.SCORING_DB_PATH)
test_db.close()
del test_db

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
app.jinja_env.filters['markdown']=markdown.markdown

# remove extra whitespace from jinja output
app.jinja_env.trim_blocks=True
app.jinja_env.lstrip_blocks=True

#######################################


# per appcontext database session
def get_db():
  db = getattr(g, '_database', None)
  if db is None:
    db = g._database = ScoringDatabase(config.SCORING_DB_PATH)
  return db


@app.teardown_appcontext
def close_db(exception):
  db = getattr(g, '_database', None)
  if db is not None:
    db.close()


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


def new_access_code(db):
  # search for unique access code
  access_code = random.randint(1000,9999)
  while db.query_single("SELECT count(*) FROM access_control_users WHERE access_code=?", (access_code,)):
    access_code = (access_code + random.randint(1,999)) % 10000
  return access_code


@app.before_request
def access_control_host_check():
  db = get_db()
  # allow localhost connections on port 8020
  if request.host in ('localhost:8020','127.0.0.1:8020') and request.remote_addr in ('localhost', '127.0.0.1'):
    logging.debug("local connection, auth ok")
    g.user = {'local':True}
    return # allow host
  else:
    g.user = db.select_one('access_control_users', session_uuid=session.get('uuid'))
    if g.user is None:
      logging.debug("remote connection, new host")
      session['uuid'] = str(uuid.uuid4())
      session.permanent = True
      g.user = {'access_code': new_access_code(db), 'local':False}
      db.insert('access_control_users', session_uuid=session['uuid'], remote_addr=request.remote_addr, access_code=g.user['access_code'], user_agent=request.user_agent.string)
      return render_template('admin_access_denied.html')
    elif g.user['allowed']:
      g.user['local'] = False
      g.user['perm'] = db.query_single_list("SELECT name FROM access_control_permissions WHERE user_id=? AND allowed", (g.user['user_id'],))
      logging.debug("remote connection, host ok")
      return # allow host
    else:
      g.user['local'] = False
      logging.debug("remote connection, host denied")
      return render_template('admin_access_denied.html')


#######################################


@app.route('/')
def index_page():
  return render_template('admin_menu.html')


@app.route('/menu')
def menu_page():
  return render_template('admin_menu.html')


#######################################

@app.route('/rest/<action>')
def rest_page(action):
  pass



#######################################


@app.route('/registration', methods=['GET','POST'])
def registration_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  
  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  g.driver_entry_list = db.driver_entry_list(g.event['event_id'])
  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  
  g.entry_driver_id_list = []
  for driver_entry in g.driver_entry_list:
    g.entry_driver_id_list.append(driver_entry['driver_id'])

  # create lookup dict for driver_id's
  g.driver_dict = {}
  for driver in g.driver_list:
    g.driver_dict[driver['driver_id']] = driver

  return render_template('admin_registration.html')


#######################################


@app.route('/access_control', methods=['GET','POST'])
def access_control_page():
  # only local connections can change access controls
  if not g.user['local'] and 'admin' not in g.user['perm']:
    return render_template('admin_access_denied.html')

  # FIXME TODO
  flash("Feature not implemented!",F_ERROR)

  return redirect(url_for('menu_page'))
  #return render_template('admin_access_control.html')


@app.route('/next_entry', methods=['GET','POST'])
def next_entry_page():
  flash("Feature not implemented!",F_ERROR)
  return redirect(url_for('menu_page'))
  

#######################################


@app.route('/events', methods=['GET','POST'])
def events_page():
  db = get_db()
  action = request.form.get('action')

  if action == 'activate':
    event_id = request.form.get('event_id')
    if db.event_exists(event_id):
      db.reg_set('active_event_id', event_id)
      flash("Set active event to %r" % event_id)
    else:
      flash("Invalid event_id", F_ERROR)
    return redirect(url_for('events_page'));

  elif action == 'deactivate':
    db.reg_set('active_event_id', None)
    flash("Event de-activated")
    return redirect(url_for('events_page'));

  elif action == 'update':
    event_id = request.form.get('event_id')
    if not db.event_exists(event_id):
      flash("Invalid event id", F_ERROR)
      return redirect(url_for('events_page'))
    event_data = {}
    for key in db.table_columns('events'):
      if key in ['event_id']:
        continue # ignore
      elif key in request.form:
        event_data[key] = request.form.get(key)
    db.update('events', event_id, **event_data)
    flash("Event changes saved")
    return redirect(url_for('events_page'))

  elif action == 'insert':
    event_data = {}
    for key in db.table_columns('events'):
      if key in ['event_id']:
        continue # ignore
      elif key in request.form:
        event_data[key] = request.form.get(key)
    event_id = db.insert('events', **event_data)
    flash("Added new event [%r]" % event_id)
    return redirect(url_for('events_page'))

  elif action == 'delete':
    if request.form.get('confirm_delete'):
      event_id = request.form.get('event_id')
      if db.event_exists(event_id):
        if db.reg_get('active_event_id') == event_id:
          db.reg_set('active_event_id',None)
        db.update("events", event_id, deleted=1)
        # FIXME do we need to propagate this to runs and entries?
        flash("Event deleted")
      else:
        flash("Invalid event_id for delete operation.", F_ERROR)
    else:
      flash("Delete ignored, no confirmation", F_WARN)
    return redirect(url_for('events_page'))

  elif action == 'recalc':
    event_id = request.form.get('event_id')
    if not db.event_exists(event_id):
      flash("Invalid event id", F_ERROR)
      return redirect(url_for('events_page'))
    # flag all entries for this event to be recalculated
    db.set_event_recalc(event_id)
    uwsgi.mule_msg('recalc')
    flash("Event scores recalculating")
    return redirect(url_for('events_page'))

  elif action is not None:
    flash("Invalid form action %r" % action, F_ERROR)
    return redirect(url_for('events_page'))

  g.event = get_event(db)
  g.event_list = db.select_all('events', deleted=0, _order_by='event_id')
  g.default_date = datetime.date.today().isoformat()
  g.default_season = datetime.date.today().year

  g.rule_sets = scoring_rules.get_rule_sets()
  g.default_rule_set = db.reg_get('default_rule_set')
  
  return render_template('admin_events.html')


#######################################


@app.route('/timing', methods=['GET','POST'])
def timing_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))


  if 'entry_filter' in request.args:
    session['entry_filter'] = request.args.get('entry_filter')
    if session['entry_filter'] not in (None, 'all', 'noassign'):
      try:
        session['entry_filter'] = int(session['entry_filter'])
      except ValueError:
        flash("Invalid entry filter", F_ERROR)
        session['entry_filter'] = None

  if 'started_filter' in request.args:
    session['started_filter'] = bool(request.args.get('started_filter'))

  if 'finished_filter' in request.args:
    session['finished_filter'] = bool(request.args.get('finished_filter'))

  if 'scored_filter' in request.args:
    session['scored_filter'] = bool(request.args.get('scored_filter'))

  if 'tossout_filter' in request.args:
    session['tossout_filter'] = bool(request.args.get('tossout_filter'))

  if 'run_limit' in request.args:
    session['run_limit'] = parse_int(request.args.get('run_limit'), 20)

  action = request.form.get('action')

  if action == 'toggle_start':
    db.reg_toggle('disable_start', True)
    return redirect(url_for('timing_page'))

  elif action == 'toggle_finish':
    db.reg_toggle('disable_finish', True)
    return redirect(url_for('timing_page'))

  elif action == 'set_next':
    if request.form.get('next'):
      db.reg_set('next_entry_id',request.form.get('next'))
      db.reg_set('next_entry_msg', None)
    return redirect(url_for('timing_page'))

  elif action == 'clear_next':
    db.reg_set('next_entry_id', None)
    db.reg_set('next_entry_msg', None)
    return redirect(url_for('timing_page'))

  elif action == 'set_filter':
    session['entry_filter'] = request.form.get('entry_filter')
    session['started_filter'] = bool(request.form.get('started_filter'))
    session['finished_filter'] = bool(request.form.get('finished_filter'))
    session['scored_filter'] = bool(request.form.get('scored_filter'))
    session['tossout_filter'] = bool(request.form.get('tossout_filter'))
    session['run_limit'] = parse_int(request.form.get('run_limit'), 20)

    if session['entry_filter'] not in (None, 'all', 'noassign'):
      try:
        session['entry_filter'] = int(session['entry_filter'])
      except ValueError:
        flash("Invalid driver filter", F_ERROR)
        session['entry_filter'] = None

    return redirect(url_for('timing_page'))

  elif action == 'reset_filter':
    session['entry_filter'] = None
    session['started_filter'] = True
    session['finished_filter'] = True
    session['scored_filter'] = True
    session['tossout_filter'] = True
    session['run_limit'] = 20
    return redirect(url_for('timing_page'))

  elif action == 'set_max_runs': # FIXME consider removing this so we only set max runs on events page
    try:
      max_runs = int(request.form.get('max_runs',''))
    except ValueError:
      flash("Invalid max runs", F_ERROR)
    else:
      db.update('events', g.event['event_id'], max_runs=max_runs)
      # make sure we recalculate all entries event totals based on new max runs
      # this is mainly needed with drop runs > 0
      db.set_event_recalc(g.event['event_id'])
      uwsgi.mule_msg('recalc')
      flash("Event scores recalculating")
    return redirect(url_for('timing_page'))

  elif action == 'update':
    run_id = request.form.get('run_id')
    if not db.run_exists(run_id):
      flash("Invalid run id", F_ERROR)
      return redirect(url_for('timing_page'))
    run_data = {'dns_dnf':0} # add default for dns_dnf checkboxes if not selected
    for key in db.table_columns('runs') + ['start_time','finish_time','split_1_time','split_2_time']:
      if key in ['run_id']:
        continue # ignore
      elif key == 'start_time':
        try:
          run_data['start_time_ms'] = parse_time_ex(request.form.get(key))
        except:
          logging.debug(request.form.get(key))
          flash("Invalid start time, start time not changed.", F_ERROR)
      elif key == 'finish_time':
        if request.form.get('old_state') != 'started':
          try:
            run_data['finish_time_ms'] = parse_time_ex(request.form.get(key))
          except:
            logging.debug(request.form.get(key))
            flash("Invalid finish time, finish time not changed.", F_ERROR)
      elif key == 'split_1_time':
        try:
          run_data['split_1_time_ms'] = parse_time_ex(request.form.get(key))
        except:
          logging.debug(request.form.get(key))
          flash("Invalid split 1 time, split 1 time not changed.", F_ERROR)
      elif key == 'split_2_time':
        try:
          run_data['split_2_time_ms'] = parse_time_ex(request.form.get(key))
        except:
          logging.debug(request.form.get(key))
          flash("Invalid split 2 time, split 2 time not changed.", F_ERROR)
      elif key == 'state' and request.form.get('state') == request.form.get('old_state'):
        pass # ignore setting state so we dont clobber a finish
      elif key == 'entry_id' and request.form.get(key) == 'None':
        run_data[key] = None
      elif key == 'dns_dnf' and request.form.get(key) and request.form.get('state') == 'started':
        pass # ignore setting dns_dnf if we are still in the started state
      elif key in request.form:
        run_data[key] = clean_str(request.form.get(key))

    if request.form.get('state') == 'started' and run_data.get('start_time_ms') == 0:
      run_data['start_time_ms'] = None
    if request.form.get('state') == 'started' and run_data.get('finsih_time_ms') == 0:
      run_data['finish_time_ms'] = None

    if run_data.get('state', request.form.get('old_state')) == 'scored' and run_data.get('finish_time_ms') is None and run_data.get('dns_dnf') == 0:
      flash("Invalid raw time, unable to set state to 'scored'", F_ERROR)
      flash("Setting state to 'finished'", F_WARN)
      run_data['state'] = 'finished'

    db.update('runs', run_id, **run_data)
    flash("Run changes saved")

    old_entry_id = request.form.get('old_entry_id')
    if old_entry_id != request.form.get('entry_id') and old_entry_id != 'None':
      db.set_entry_recalc(old_entry_id)
      uwsgi.mule_msg('recalc')
      flash("Old entry recalc")

    db.set_run_recalc(run_id)
    uwsgi.mule_msg('recalc')
    flash("Run recalc")

    if 'entry_id' in run_data and run_data['entry_id'] is not None:
      db.set_entry_recalc(run_data['entry_id'])
      uwsgi.mule_msg('recalc')
      flash("Entry recalc")

    return redirect(url_for('timing_page'))

  elif action == 'insert':
    run_data = {}
    for key in db.table_columns('runs'):
      if key in ['run_id']:
        continue # ignore
      elif key in request.form:
        run_data[key] = clean_str(request.form.get(key))
    run_id = db.insert('runs', **run_data)
    db.set_run_recalc(run_id)
    uwsgi.mule_msg('recalc')
    flash("Added new run [%r]" % run_id)
    return redirect(url_for('timing_page'))

  elif action is not None:
    flash("Invalid form action %r" % action, F_ERROR)
    return redirect(url_for('timing_page'))

  if 'entry_filter' not in session:
    session['entry_filter'] = None
  if 'started_filter' not in session:
    session['started_filter'] = True
  if 'finished_filter' not in session:
    session['finished_filter'] = True
  if 'scored_filter' not in session:
    session['scored_filter'] = True
  if 'tossout_filter' not in session:
    session['tossout_filter'] = True
  if 'hide_invalid_times' not in session:
    session['hide_invalid_times'] = False
  if 'run_limit' not in session:
    session['run_limit'] = 20

  state_filter = []
  if session['started_filter']:
    state_filter += ['started']
  if session['finished_filter']:
    state_filter += ['finished']
  if session['scored_filter']:
    state_filter += ['scored']
  if session['tossout_filter']:
    state_filter += ['tossout']
  
  g.run_list = db.run_list(event_id=g.event['event_id'], entry_id=session['entry_filter'], state=state_filter, sort='d', limit=session['run_limit'])
  g.driver_entry_list = db.driver_entry_list(g.event['event_id'])

  g.cars_started = db.run_count(event_id=g.event['event_id'], state='started')
  g.cars_finished = db.run_count(event_id=g.event['event_id'], state='finished')
  
  g.disable_start = db.reg_get_int('disable_start', 0)
  g.disable_finish = db.reg_get_int('disable_finish', 0)
  
  g.next_entry_id = db.reg_get_int('next_entry_id')
  g.next_entry_driver = db.select_one('driver_entries', entry_id=g.next_entry_id)
  if g.next_entry_id is None:
    g.next_entry_run_number = None
  else:
    # FIXME change this to max of run_number instead of count
    g.next_entry_run_number = 1 + db.run_count(entry_id=g.next_entry_id, state=('started','finished','scored'))
  
  g.barcode_scanner_status = db.reg_get('barcode_scanner_status')
  g.tag_heuer_status = db.reg_get('tag_heuer_status')
  g.rfid_reader_status = db.reg_get('rfid_reader_status')

  # FIXME change how watchdog is handled
  g.hardware_ok = True
  g.start_ready = g.hardware_ok and (g.tag_heuer_status == 'Open') and not g.disable_start
  g.finish_ready = g.hardware_ok and (g.tag_heuer_status == 'Open') and not g.disable_finish

  g.run_group = db.reg_get('run_group')
  g.next_entry_msg = db.reg_get('next_entry_msg')

  # create car description strings for entries
  g.car_dict = {}
  for entry in g.driver_entry_list:
    g.car_dict[entry['entry_id']] = "%s %s %s %s" % (entry['car_color'], entry['car_year'], entry['car_make'], entry['car_model'])

  return render_template('admin_timing.html')


#######################################

@app.route('/timer_data', methods=['GET','POST'])
def timer_data_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  g.timer_data_count = db.reg_get_int('timer_data_count', 100)
  g.time_list = db.query_all("SELECT * FROM times WHERE event_id=? ORDER BY time_id DESC LIMIT ?", (g.event['event_id'], g.timer_data_count))

  return render_template('admin_timer_data.html')

#######################################

@app.route('/registration/new_entry', methods=['GET','POST'])
def registration_new_entry_page():
  return new_entry_page('registration')

@app.route('/entries/new_entry', methods=['GET','POST'])
def entries_new_entry_page():
  return new_entry_page('entries')

@app.route('/new_entry', methods=['GET','POST'])
def new_entry_page(parent=None):
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  g.parent = parent

  g.default_driver_id = parse_int(request.args.get('driver_id'))

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  if action == 'insert':
    entry_data = {}
    for key in db.table_columns('entries'):
      if key in ['entry_id']:
        continue # ignore
      elif key in request.form:
        entry_data[key] = clean_str(request.form.get(key))
    if 'driver_id' not in entry_data or entry_data['driver_id'] is None:
      flash("Invalid driver for new entry, no entry created.", F_ERROR)
    elif 'car_class' not in entry_data or entry_data['car_class'] not in g.rules.car_class_list:
      flash("Invalid car class for new entry, no entry created.", F_ERROR)
    else:
      entry_data['run_group'] = db.reg_get("%s_run_group" % entry_data['car_class'])
      if db.count('entries', event_id=g.event['event_id'], driver_id=entry_data['driver_id']):
        flash("Entry already exists for driver! Creating new entry anyways.", F_WARN)
      entry_id = db.insert('entries',**entry_data)
      flash("Added new entry [%r]" % entry_id)
    if parent == 'registration':
      return redirect(url_for('registration_page'))
    elif parent == 'entries':
      return redirect(url_for('entries_page'))
    else:
      return redirect(url_for('new_entry_page'))
  
  elif action is not None:
    flash("Invalid form action %r" % action, F_ERROR)
    if parent == 'registration':
      return redirect(url_for('registration_new_entry_page'))
    elif parent == 'entries':
      return redirect(url_for('entries_new_entry_page'))
    else:
      return redirect(url_for('new_entry_page'))

  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  
  # create lookup dict for driver_id's
  g.driver_dict = {}
  for driver in g.driver_list:
    g.driver_dict[driver['driver_id']] = driver

  return render_template('admin_new_entry.html')


@app.route('/entries', methods=['GET','POST'])
def entries_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  if action == 'delete':
    if request.form.get('confirm_delete') == 'do_it':
      entry_id = request.form.get('entry_id')
      if db.entry_exists(entry_id):
        db.update('entries', entry_id, deleted=1)
        # FIXME add propagation of deletes to runs?
        flash("Entry deleted")
      else:
        flash("Invalid entry_id for delete operation.", F_ERROR)
    else:
      flash("Delete ignored, no confirmation", F_WARN)
    return redirect(url_for('entries_page'))

  elif action == 'update':
    entry_id = request.form.get('entry_id')
    if not db.entry_exists(entry_id):
      flash("Invalid entry id", F_ERROR)
      return redirect(url_for('entries_page'))
    entry_data = {}
    for key in db.table_columns('entries'):
      if key in ['entry_id']:
        continue # ignore
      elif key in request.form:
        entry_data[key] = clean_str(request.form.get(key))
    #entry_data['run_group'] = db.reg_get("%s_run_group" % entry_data['car_class'])
    db.update('entries', entry_id, **entry_data)
    flash("Entry changes saved")
    return redirect(url_for('entries_page'))

  elif action == 'check_in':
    entry_id = request.form.get('entry_id')
    if not db.entry_exists(entry_id):
      flash("Invalid entry id", F_ERROR)
      return redirect(url_for('entries_page'))
    db.update('entries', entry_id, checked_in=1)
    flash("Entry checked in")
    return redirect(url_for('entries_page'))

  elif action == 'tracking_check_in':
    tracking_number = request.form.get('tracking_number')
    if tracking_number is not None:
      tracking_number = tracking_number.lstrip('0')
      entry = db.select_one('driver_entries', tracking_number=tracking_number)
      if not entry:
        flash("Entry not found for tracking number %s" % tracking_number, F_ERROR)
        return redirect(url_for('entries_page'))
      db.update('entries', entry['entry_id'], checked_in=1)
      flash("Entry checked in")
    return redirect(url_for('entries_page'))

  elif action is not None:
    flash("Invalid form action %r" % action, F_ERROR)
    return redirect(url_for('entries_page'))

  g.driver_entry_list = db.driver_entry_list(g.event['event_id'])
  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  
  # create lookup dict for driver_id's
  g.driver_dict = {}
  for driver in g.driver_list:
    g.driver_dict[driver['driver_id']] = driver

  return render_template('admin_entries.html')


#######################################

@app.route('/registration/new_driver', methods=['GET','POST'])
def registration_new_driver_page():
  return new_driver_page('registration')

@app.route('/drivers/new_driver', methods=['GET','POST'])
def drivers_new_driver_page():
  return new_driver_page('drivers')

@app.route('/new_driver', methods=['GET','POST'])
def new_driver_page(parent=None):
  db = get_db()

  g.parent = parent
  
  action = request.form.get('action')

  if action == 'insert':
    driver_data = {}
    for key in db.table_columns('drivers'):
      if key in ['driver_id']:
        continue # ignore
      elif key in request.form:
        driver_data[key] = clean_str(request.form.get(key))
    # remove leading zeros from tracking_number
    if 'tracking_number' in driver_data and driver_data['tracking_number'] is not None:
      driver_data['tracking_number'] = driver_data['tracking_number'].lstrip('0')
      flash("tracking_number = %r" % driver_data['tracking_number'])
    driver_id = db.insert('drivers',**driver_data)
    flash("Added new driver [%r]" % driver_id)
    if parent == 'registration':
      return redirect(url_for('registration_new_entry_page',driver_id=driver_id))
    elif parent == 'drivers':
      return redirect(url_for('drivers_page'))
    else:
      return redirect(url_for('new_driver_page'))

  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    if parent == 'registration':
      return redirect(url_for('registration_new_driver_page'))
    elif parent == 'drivers':
      return redirect(url_for('drivers_new_driver_page'))
    else:
      return redirect(url_for('new_driver_page'))

  return render_template('admin_new_driver.html')


@app.route('/drivers', methods=['GET','POST'])
def drivers_page():
  db = get_db()

  action = request.form.get('action')

  if action == 'delete':
    if request.form.get('confirm_delete'):
      driver_id = request.form.get('driver_id')
      if db.driver_exists(driver_id):
        db.update('drivers', driver_id, deleted=1)
        db.execute("UPDATE entries SET deleted=1 WHERE driver_id=?", (driver_id,))
        # FIXME do we need to propegate this further?
        flash("Driver deleted")
      else:
        flash("Invalid driver_id for delete operation.", F_ERROR)
    else:
      flash("Delete ignored, no confirmation", F_WARN)
    return redirect(url_for('drivers_page'))

  elif action == 'update':
    driver_id = request.form.get('driver_id')
    if not db.driver_exists(driver_id):
      flash("Invalid driver id", F_ERROR)
      return redirect(url_for('drivers_page'))
    driver_data = {}
    for key in db.table_columns('drivers'):
      if key in ['driver_id']:
        continue # ignore
      elif key in request.form:
        driver_data[key] = clean_str(request.form.get(key))
    # remove leading zeros from tracking_number
    if 'tracking_number' in driver_data:
      driver_data['tracking_number'] = driver_data['tracking_number'].lstrip('0')
      flash("tracking_number = %r" % driver_data['tracking_number'])
    db.update('drivers', driver_id, **driver_data)
    flash("Driver changes saved")
    return redirect(url_for('drivers_page'))
  
  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('drivers_page'))

  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  return render_template('admin_drivers.html')


#######################################


@app.route('/penalties', methods=['GET','POST'])
def penalties_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  if action == 'insert':
    entry_id = request.form.get('entry_id')
    penalty_time = request.form.get('penalty_time')
    penalty_note = request.form.get('penalty_note')

    if not db.entry_exists(entry_id):
      flash("Invalid entry id", F_ERROR)
      return redirect(url_for('penalties_page'))

    try:
      time_ms = parse_time_ex(penalty_time)
    except:
      flash("Invalid penalty time", F_ERROR)
      return redirect(url_for('penalties_page'))
    
    if time_ms is None:
      time_ms = 0

    db.insert('penalties', event_id=g.event['event_id'], entry_id=entry_id, time_ms=time_ms, penalty_note=penalty_note)
    flash("Penalty added")

    db.set_entry_recalc(entry_id)
    uwsgi.mule_msg('recalc')
    flash("Entry recalculating")

    return redirect(url_for('penalties_page'))

  elif action == 'update':
    penalty_id = request.form.get('penalty_id')
    entry_id = request.form.get('entry_id')
    penalty_time = request.form.get('penalty_time')
    penalty_note = request.form.get('penalty_note')
    old_penalty = db.select_one('penalties', penalty_id=penalty_id)

    if penalty_id is None:
      flash("Invalid penalty id", F_ERROR)
      return redirect(url_for('penalties_page'))

    if not db.entry_exists(entry_id):
      flash("Invalid entry id", F_ERROR)
      return redirect(url_for('penalties_page'))

    try:
      time_ms = parse_time_ex(penalty_time)
    except:
      flash("Invalid penalty time", F_ERROR)
      return redirect(url_for('penalties_page'))

    if time_ms is None:
      time_ms = 0

    db.update('penalties', penalty_id, entry_id=entry_id, time_ms=time_ms, penalty_note=penalty_note)
    flash("Penalty updated")

    if old_penalty['entry_id'] != parse_int(entry_id):
      # update previous entry
      flash("old entry recalc, %r != %r" % (old_penalty['entry_id'],entry_id))
      db.set_entry_recalc(old_penalty['entry_id'])
      uwsgi.mule_msg('recalc')

    # update current entry
    db.set_entry_recalc(entry_id)
    uwsgi.mule_msg('recalc')
    flash("entry recalc")

    return redirect(url_for('penalties_page'))

  elif action == 'delete':
    penalty_id = request.form.get('penalty_id')
    old_penalty = db.select_one('penalties', penalty_id=penalty_id)

    if old_penalty is None:
      flash("Invalid penalty id", F_ERROR)
      return redirect(url_for('penalties_page'))

    db.update('penalties', penalty_id, deleted=1)
    flash("Penalty deleted")

    # update previous entry
    flash("old entry recalc")
    db.set_entry_recalc(old_penalty['entry_id'])
    uwsgi.mule_msg('recalc')

    return redirect(url_for('penalties_page'))

  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('penalties_page'))

  g.penalty_list = db.select_all('penalties', event_id=g.event['event_id'], deleted=0, _order_by="penalty_id")
  g.driver_entry_list = db.driver_entry_list(g.event['event_id'])

  return render_template('admin_penalties.html')


#######################################


@app.route('/run_groups', methods=['GET','POST'])
def run_groups_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  # FIXME change sessions to run_groups

  if action == 'update':
    for car_class in g.rules.car_class_list:
      class_run_group = request.form.get("%s_run_group" % car_class)
      if class_run_group not in ('1','2','3','4','-1'):
        class_run_group = '-1'
      db.reg_set("%s_run_group" % car_class, class_run_group)
      db.entry_run_group_update(g.event['event_id'], car_class, class_run_group)

    flash("Class run groups updated")
    return redirect(url_for('run_groups_page'))

  elif action == 'set_run_group':
    run_group = request.form.get('run_group')
    if run_group not in ('1','2','3','4'):
      run_group = '1'
    db.reg_set('run_group', run_group)
    flash("Active run group updated")
    return redirect(url_for('run_groups_page'))

  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('run_groups_page'))

  g.class_run_groups = {}
  for car_class in g.rules.car_class_list:
    g.class_run_groups[car_class] = parse_int(db.reg_get("%s_run_group" % car_class), -1)

  g.run_group = parse_int(db.reg_get('run_group'), 1)

  return render_template('admin_run_groups.html')


#######################################

@app.route('/settings', methods=['GET','POST'])
def settings_page():
  db = get_db()

  if request.form.get('action') == 'update':
    port = request.form.get('serial_port_rfid_reader')
    if port in ('', 'None'):
      port = None
    db.reg_set('serial_port_rfid_reader', port)
    port = request.form.get('serial_port_tag_heuer')
    if port in ('', 'None'):
      port = None
    db.reg_set('serial_port_tag_heuer', port)
    port = request.form.get('serial_port_barcode')
    if port in ('', 'None'):
      port = None
    db.reg_set('serial_port_barcode', port)
    flash("Settings updated")
    return redirect(url_for('settings_page'))

  g.serial_port_rfid_reader = db.reg_get('serial_port_rfid_reader')
  g.serial_port_tag_heuer = db.reg_get('serial_port_tag_heuer')
  g.serial_port_barcode = db.reg_get('serial_port_barcode')

  g.serial_list = glob("/dev/ttyUSB*") + glob("/dev/ttyACM*") + glob("/dev/serial/by-id/*")

  return render_template('admin_settings.html')

#######################################


@app.route('/scores', methods=['GET','POST'])
def scores_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))
  
  action = request.form.get('action')

  if action == 'event_recalc':
    db.set_event_recalc(g.event['event_id'])
    uwsgi.mule_msg('recalc')
    flash("Event scores recalculating")
    return redirect(url_for('scores_page'))

  elif action == 'entry_recalc':
    entry_id = request.form.get('entry_id')
    if not db.entry_exists(entry_id):
      flash("Invalid entry id", F_ERROR)
      return redirect(url_for('entries_page'))
    db.set_entry_recalc(entry_id)
    uwsgi.mule_msg('recalc')
    flash("Entry score recalculating")
    return redirect(url_for('scores_page'))
  
  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('scores_page'))

  # sort entries into car class
  g.class_entry_list = {}
  g.driver_entry_list = db.driver_entry_list(g.event['event_id'])
  for entry in g.driver_entry_list:
    if entry['car_class'] not in g.class_entry_list:
      g.class_entry_list[entry['car_class']] = []
    if entry['scores_visible']:
      g.class_entry_list[entry['car_class']].append(entry)

  # sort each car class by event_time_ms and run_count
  for car_class in g.class_entry_list:
    g.class_entry_list[car_class].sort(cmp=entry_cmp)

  g.entry_run_list = {}
  for entry in g.driver_entry_list:
    g.entry_run_list[entry['entry_id']] = db.run_list(entry_id=entry['entry_id'], state=('scored','finished','started'), limit=g.rules.max_runs)
  
  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  
  # create lookup dict for driver_id's
  g.driver_dict = {}
  for driver in g.driver_list:
    g.driver_dict[driver['driver_id']] = driver

  return render_template('admin_scores.html')

#######################################

@app.route('/import', methods=['GET','POST'])
def import_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  logging.debug("Action: %r" % action)
  logging.debug("Files: %r" % request.files.keys())

  if action == 'upload' and 'upload_file' in request.files:
    logging.debug("UPLOAD")

    upload_file = request.files['upload_file']
    logging.debug("Filename: %r" % upload_file.filename)

    if not upload_file.filename.lower().endswith('csv'):
      flash("File suffix is not .csv",F_ERROR)
      return redirect(url_for('import_page'))

    reader = csv.DictReader(upload_file)

    valid_status = ('Confirmed','Checked In','New')

    # validate required fields
    required_fields = ('Unique ID','Class','No.','Last Name','First Name','Color','Year','Make','Model','Status')
    logging.debug(reader.fieldnames)
    for field in required_fields:
      if field not in reader.fieldnames:
        flash("Missing required field, %s" % field, F_ERROR)
        return redirect(url_for('import_page'))

    row_count = 0
    for row in reader:
      row_count += 1
      # check if row has valid status
      # check if we have a driver with msreg unique id
      # if not create driver
      #   - check for optional city, state, zip, member #
      # check car class against rule_set
      # check if we have an entry for driver in the given class
      # if not create entry
      #   - check for optional co-driver

      if row['Status'] not in valid_status:
        flash("Skipping row %d: invalid status, %r" % (row_count, row['Status']), 'inline')
        continue

      driver_id = db.query_single("SELECT driver_id FROM drivers WHERE msreg_number=? AND NOT deleted", (row['Unique ID'],))
      if driver_id is None:
        data = {}
        data['msreg_number'] = clean_str(row['Unique ID'])
        data['first_name'] = clean_str(row['First Name'])
        data['last_name'] = clean_str(row['Last Name'])
        driver_id = db.insert('drivers', **data)
        data['driver_id'] = driver_id
        flash("Creating driver [%(driver_id)s]: %(msreg_number)s %(first_name)s %(last_name)s" % data, 'inline')
      else:
        flash("Driver found [%d]" % driver_id, 'inline')

      if row['Class'] in g.rules.car_class_list:
        car_class = row['Class']
      elif row['Class'] in g.rules.car_class_alias:
        car_class = g.rules.car_class_alias[row['Class']]
      else:
        flash("Skipping row %d: invalid class, %r" % (row_count, row['Class']), 'inline')
        continue

      entry_id = db.query_single("SELECT entry_id FROM entries WHERE event_id=? AND driver_id=? AND car_class=?", (g.event['event_id'], driver_id, car_class))

      if entry_id is None:
        data = {}
        data['driver_id'] = driver_id
        data['event_id'] = g.event['event_id']
        data['car_class'] = car_class
        data['car_color'] = clean_str(row['Color'])
        data['car_year'] = clean_str(row['Year'])
        data['car_make'] = clean_str(row['Make'])
        data['car_model'] = clean_str(row['Model'])
        data['car_number'] = clean_str(row['No.'])
        if data['car_number'] is None:
          data['car_number'] = 0
        if 'Co-Drivers' in row:
          data['co_driver'] = clean_str(row['Co-Drivers'])
        entry_id = db.insert('entries', **data)
        data['entry_id'] = entry_id
        flash("Creating entry [%(entry_id)s]: %(car_class)s, %(car_number)s" % data, 'inline')
      else:
        flash("Entry found [%d]" % entry_id, 'inline')

    return redirect(url_for('import_page'))
  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('import_page'))

  return render_template('admin_import.html')

#######################################

@app.route('/export')
def export_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))

  return render_template('admin_export.html')

#######################################

@app.route('/export/scores/csv')
def export_scores_csv_page():
  db = get_db()
  g.event = get_event(db)
  g.rules = get_rules(g.event)

  if g.event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  if g.rules is None:
    flash("Invalid rule set for active event!", F_ERROR)
    return redirect(url_for('events_page'))
  
  # sort entries into car class
  g.class_entry_list = {}
  g.driver_entry_list = db.driver_entry_list(g.event['event_id'])
  for entry in g.driver_entry_list:
    if entry['car_class'] not in g.class_entry_list:
      g.class_entry_list[entry['car_class']] = []
    if entry['scores_visible']:
      g.class_entry_list[entry['car_class']].append(entry)

  # sort each car class by event_time_ms and run_count
  for car_class in g.class_entry_list:
    g.class_entry_list[car_class].sort(cmp=entry_cmp)

  g.entry_run_list = {}
  for entry in g.driver_entry_list:
    g.entry_run_list[entry['entry_id']] = db.run_list(entry_id=entry['entry_id'], state=('scored',), limit=g.rules.max_runs)

  output = StringIO()

  writer = csv.writer(output)

  row = []
  row.append('car_class')
  row.append('car_number')
  row.append('first_name')
  row.append('alt_name')
  row.append('last_name')
  row.append('car_year')
  row.append('car_make')
  row.append('car_model')
  row.append('car_color')
  
  for i in range(g.rules.max_runs):
    row.append('run_%d_raw' % (i+1))
    row.append('run_%d_cones' % (i+1))
    row.append('run_%d_gates' % (i+1))
    row.append('run_%d_total' % (i+1))

  row.append('event_penalties')
  row.append('event_total_time')

  writer.writerow(row)

  for car_class in g.rules.car_class_list:
    if car_class in g.class_entry_list:
      for entry in g.class_entry_list[car_class]:
        row = []
        row.append(entry['car_class'])
        row.append(entry['car_number'])
        row.append(entry['first_name'])
        row.append(entry['alt_name'])
        row.append(entry['last_name'])
        row.append(entry['car_year'])
        row.append(entry['car_make'])
        row.append(entry['car_model'])
        row.append(entry['car_color'])
        
        count = g.rules.max_runs
        for run in g.entry_run_list[entry['entry_id']]:
          row.append(run['raw_time'])
          row.append(run['cones'])
          row.append(run['gates'])
          if g.rules.drop_runs > 0 and run['drop_run']:
            row.append('(' + str(run['total_time']) + ')')
          else:
            row.append(run['total_time'])
          count -= 1

        # add blanks for missing runs
        for i in range(count):
          row.append('')
          row.append('')
          row.append('')
          row.append('')
        
        row.append(entry['event_penalties'])
        row.append(entry['event_time'])
        
        writer.writerow(row)

  response = make_response(output.getvalue(), 200)
  response.headers['Content-Disposition'] = 'attachment; filename="%s_scores.csv"' % g.event['event_date']
  response.mimetype = 'text/csv'

  return response


#######################################


@app.route('/debug', methods=['GET','POST'])
def debug_registry_page():
  if not g.user['local']:
    return render_template('admin_access_denied.html')

  db = get_db()
  if request.method == 'POST' and request.form.get('action') == 'update':
    for key in request.form:
      if key != 'action':
        db.reg_set(key, clean_str(request.form[key]))
    return redirect(url_for("debug_registry_page"))
  elif request.method == 'GET' and request.args.get('action') == 'update':
    for key in request.args:
      if key != 'action':
        db.reg_set(key, clean_str(request.args[key]))
    return redirect(url_for("debug_registry_page"))
  elif request.method == 'POST' and request.form.get('action') == 'insert':
    key = clean_str(request.form.get('reg_name'))
    value = clean_str(request.form.get('reg_value'))
    if key is not None:
      db.reg_set(key, value)
      logging.debug("insert reg, %r = %r", key, value)

  reg_list = db.reg_list(request.args.get('all',False))

  # query settings
  return render_template('admin_debug_registry.html', reg_list=reg_list)


#######################################



if __name__ == '__main__':
  # start dev server at localhost:8020
  app.run(host="127.0.0.1", port=8020, debug=True)

