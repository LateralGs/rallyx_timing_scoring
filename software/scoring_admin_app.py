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
from time import time, sleep
import datetime
import csv
from cStringIO import StringIO
from serial.tools.list_ports import comports
from glob import glob
import markdown
import threading

import uwsgidecorators
import uwsgi

#######################################
# flash categories
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


def get_rules(db):
  rules = getattr(g, '_rules', None)
  if rules is None:
    rules = g._rules = config.SCORING_RULES_CLASS()
  rules.sync(db)
  return rules


#######################################


@app.route('/')
def index_page():
  # nothing to do, static page for instructions
  return render_template('admin_index.html')


#######################################


@app.route('/events', methods=['GET','POST'])
def events_page():
  db = get_db()
  g.rules = get_rules(db)

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

  elif action == 'finalize':
    event_id = request.form.get('event_id')
    if not db.event_exists(event_id):
      flash("Invalid event id", F_ERROR)
      return redirect(url_for('events_page'))
    g.rules.event_finalize(db, event_id)
    flash("Event scores finalized")
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

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id, deleted=0)
  g.event_list = db.select_all('events', deleted=0, _order_by='event_id')
  g.default_date = datetime.date.today().isoformat()
  
  return render_template('admin_events.html')


#######################################


@app.route('/timing', methods=['GET','POST'])
def timing_page():
  db = get_db()
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
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

  elif action == 'toggle_invalid':
    session['hide_invalid_times'] = not session.get('hide_invalid_times', False)
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

  elif action == 'set_max_runs':
    try:
      max_runs = int(request.form.get('max_runs',''))
    except ValueError:
      flash("Invalid max runs", F_ERROR)
    else:
      db.update('events', g.active_event_id, max_runs=max_runs)
      # make sure we recalculate all entries event totals based on new max runs
      # this is mainly needed with drop runs > 0
      db.set_event_recalc(g.active_event_id)
      uwsgi.mule_msg('recalc')
      flash("Event scores recalculating")
    return redirect(url_for('timing_page'))

  elif action == 'dnf':
    run_id = request.form.get('run_id')
    if not db.run_exists(run_id):
      flash("Invalid run id", F_ERROR)
      return redirect(url_for('timing_page'))
    db.update('runs', run_id, start_time_ms=None, finish_time_ms=0, state='finished')
    # FIXME should this be deferred?
    g.rules.recalc_run(db, run_id)
    flash("Run recalc")
    entry_id = request.form.get('old_entry_id')
    db.set_entry_recalc(entry_id)
    uwsgi.mule_msg('recalc')
    flash("Entry recalc")

  elif action == 'dns':
    run_id = request.form.get('run_id')
    if not db.run_exists(run_id):
      flash("Invalid run id", F_ERROR)
      return redirect(url_for('timing_page'))
    db.update('runs', run_id, start_time_ms=0, finish_time_ms=None, state='finished')
    # FIXME should this be deferred?
    g.rules.recalc_run(db, run_id)
    flash("Run recalc")
    entry_id = request.form.get('old_entry_id')
    db.set_entry_recalc(entry_id)
    uwsgi.mule_msg('recalc')
    flash("Entry recalc")


  elif action == 'update':
    run_id = request.form.get('run_id')
    if not db.run_exists(run_id):
      flash("Invalid run id", F_ERROR)
      return redirect(url_for('timing_page'))
    run_data = {}
    for key in db.table_columns('runs') + ['start_time','finish_time']:
      if key in ['run_id']:
        continue # ignore
      elif key == 'start_time':
        try:
          run_data['start_time_ms'] = parse_time_ex(request.form.get(key))
        except:
          app.logger.debug(request.form.get(key))
          flash("Invalid start time, start time not changed.", F_ERROR)
      elif key == 'finish_time':
        if request.form.get('old_state') != 'started':
          try:
            run_data['finish_time_ms'] = parse_time_ex(request.form.get(key))
          except:
            app.logger.debug(request.form.get(key))
            flash("Invalid finish time, finish time not changed.", F_ERROR)
      elif key == 'state' and request.form.get('state') == request.form.get('old_state'):
        pass # ignore setting state so we dont clobber a finish
      elif key == 'entry_id' and request.form.get(key) == 'None':
        run_data[key] = None
      elif key in request.form:
        run_data[key] = clean_str(request.form.get(key))

    if request.form.get('state') == 'started' and run_data.get('start_time_ms') == 0:
      run_data['start_time_ms'] = None
    if request.form.get('state') == 'started' and run_data.get('finsih_time_ms') == 0:
      run_data['finish_time_ms'] = None

    if run_data.get('state', request.form.get('old_state')) == 'scored' and run_data.get('finish_time_ms') is None and run_data.get('start_time_ms') != 0:
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

    # FIXME should this be deferred?
    g.rules.recalc_run(db, run_id)
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
    # FIXME should this be deferred?
    g.rules.recalc_run(db, run_id)
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
  
  g.disp_time_events = db.reg_get_int('disp_time_events', 20)
  g.time_list = db.query_all("SELECT * FROM times WHERE event_id=? ORDER BY time_id DESC LIMIT ?", (g.active_event_id, g.disp_time_events))

  g.run_list = db.run_list(event_id=g.active_event_id, entry_id=session['entry_filter'], state=state_filter, sort='d', limit=session['run_limit'])
  g.driver_entry_list = db.driver_entry_list(g.active_event_id)

  g.cars_started = db.run_count(event_id=g.active_event_id, state='started')
  g.cars_finished = db.run_count(event_id=g.active_event_id, state='finished')
  
  g.disable_start = db.reg_get_int('disable_start', 0)
  g.disable_finish = db.reg_get_int('disable_finish', 0)
  
  g.next_entry_id = db.reg_get_int('next_entry_id')
  g.next_entry_driver = db.select_one('driver_entries', entry_id=g.next_entry_id)
  if g.next_entry_id is None:
    g.next_entry_run_count = 0
  else:
    g.next_entry_run_count = db.run_count(entry_id=g.next_entry_id, state=('started','finished','scored'))
  
  g.barcode_scanner_status = db.reg_get('barcode_scanner_status')
  g.tag_heuer_status = db.reg_get('tag_heuer_status')
  g.rfid_reader_status = db.reg_get('rfid_reader_status')

  # FIXME change how watchdog is handled
  g.hardware_ok = True
  g.start_ready = g.hardware_ok and (g.tag_heuer_status == 'Open') and not g.disable_start
  g.finish_ready = g.hardware_ok and (g.tag_heuer_status == 'Open') and not g.disable_finish

  g.race_session = db.reg_get('race_session')
  g.next_entry_msg = db.reg_get('next_entry_msg')

  # create car description strings for entries
  g.car_dict = {}
  for entry in g.driver_entry_list:
    g.car_dict[entry['entry_id']] = "%s %s %s %s" % (entry['car_color'], entry['car_year'], entry['car_make'], entry['car_model'])

  return render_template('admin_timing.html')


#######################################


@app.route('/entries', methods=['GET','POST'])
def entries_page():
  db = get_db()
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
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

  elif action == 'insert':
    entry_data = {}
    for key in db.table_columns('entries'):
      if key in ['entry_id']:
        continue # ignore
      elif key == 'co_driver_id' and request.form.get('co_driver_id') == 'None':
        entry_data[key] = None
      elif key in request.form:
        entry_data[key] = clean_str(request.form.get(key))
    if 'driver_id' not in entry_data or entry_data['driver_id'] is None:
      flash("Invalid driver for new entry, no entry created.", F_ERROR)
    elif 'car_class' not in entry_data or entry_data['car_class'] not in g.rules.car_class_list:
      flash("Invalid car class for new entry, no entry created.", F_ERROR)
    else:
      entry_data['race_session'] = db.reg_get("%s_session" % entry_data['car_class'])
      if db.count('entries', event_id=g.active_event_id, driver_id=entry_data['driver_id']):
        flash("Entry already exists for driver! Creating new entry anyways.", F_WARN)
      entry_id = db.insert('entries',**entry_data)
      flash("Added new entry [%r]" % entry_id)
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
      elif key == 'co_driver_id' and request.form.get('co_driver_id') == 'None':
        entry_data[key] = None
      elif key in request.form:
        entry_data[key] = clean_str(request.form.get(key))
    entry_data['race_session'] = db.reg_get("%s_session" % entry_data['car_class'])
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

  elif action == 'card_check_in':
    card_number = request.form.get('card_number')
    entry = db.select_one('driver_entries', card_number=card_number)
    if not entry:
      flash("Entry not found for card number %s" % card_number, F_ERROR)
      return redirect(url_for('entries_page'))
    db.update('entries', entry['entry_id'], checked_in=1)
    flash("Entry checked in")
    return redirect(url_for('entries_page'))

  elif action is not None:
    flash("Invalid form action %r" % action, F_ERROR)
    return redirect(url_for('entries_page'))

  g.driver_entry_list = db.driver_entry_list(g.active_event_id)
  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  
  # create lookup dict for driver_id's
  g.driver_dict = {}
  for driver in g.driver_list:
    g.driver_dict[driver['driver_id']] = driver

  return render_template('admin_entries.html')


#######################################


@app.route('/drivers', methods=['GET','POST'])
def drivers_page():
  db = get_db()
  g.rules = get_rules(db)

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

  elif action == 'insert':
    driver_data = {}
    for key in db.table_columns('drivers'):
      if key in ['driver_id']:
        continue # ignore
      elif key == 'card_number':
        driver_data[key] = parse_int(request.form.get(key))
      elif key in request.form:
        driver_data[key] = clean_str(request.form.get(key))
    driver_id = db.insert('drivers',**driver_data)
    flash("Added new driver [%r]" % driver_id)
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
      elif key == 'card_number':
        driver_data[key] = parse_int(request.form.get(key))
      elif key in request.form:
        driver_data[key] = clean_str(request.form.get(key))
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
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
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

    db.insert('penalties', event_id=g.active_event_id, entry_id=entry_id, time_ms=time_ms, penalty_note=penalty_note)
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

    if penalty is None:
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

    if old_penalty['entry_id'] != entry_id:
      # update previous entry
      flash("old entry recalc")
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

  g.penalty_list = db.select_all('penalties', event_id=g.active_event_id, deleted=0, _order_by="penalty_id")
  g.driver_entry_list = db.driver_entry_list(g.active_event_id)

  return render_template('admin_penalties.html')


#######################################


@app.route('/sessions', methods=['GET','POST'])
def sessions_page():
  db = get_db()
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  if action == 'update':
    for car_class in g.rules.car_class_list:
      class_session = request.form.get("%s_session" % car_class)
      if class_session not in ('1','2','3','4','-1'):
        class_session = '-1'
      db.reg_set("%s_session" % car_class, class_session)
      db.entry_session_update(g.active_event_id, car_class, class_session)

    flash("Class sessions updated")
    return redirect(url_for('sessions_page'))

  elif action == 'set_session':
    race_session = request.form.get('race_session')
    if race_session not in ('1','2','3','4'):
      race_session = '1'
    db.reg_set('race_session', race_session)
    flash("Active race session updated")
    return redirect(url_for('sessions_page'))

  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('sessions_page'))

  g.class_sessions = {}
  for car_class in g.rules.car_class_list:
    g.class_sessions[car_class] = parse_int(db.reg_get("%s_session" % car_class), -1)

  g.race_session = parse_int(db.reg_get('race_session'), 1)

  return render_template('admin_sessions.html')

#######################################

@app.route('/settings', methods=['GET','POST'])
def settings_page():
  db = get_db()
  g.rules = get_rules(db)

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
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  
  action = request.form.get('action')

  if action == 'entry_finalize':
    #g.rules.event_finalize(db, g.active_event_id)
    #flash("Event scores finalized")
    flash("TODO: entry finalize", F_WARN)
    return redirect(url_for('scores_page'))
    
  elif action == 'event_recalc':
    db.set_event_recalc(g.active_event_id)
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

  elif action == 'prune_dns':
    flash("TODO: prune dns runs", F_WARN)
    return redirect(url_for('scores_page'))

  elif action == 'export_results':
    return redirect(url_for('export_results_page'))
  
  elif action is not None:
    flash("Unkown form action %r" % action, F_ERROR)
    return redirect(url_for('scores_page'))

  # sort entries into car class
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
  for entry in g.driver_entry_list:
    # FIXME TODO add other run states so we can show pending runs in scores
    g.entry_run_list[entry['entry_id']] = db.run_list(entry_id=entry['entry_id'], state=('scored',), limit=g.rules.max_runs)
  
  g.driver_list = db.select_all('drivers', deleted=0, _order_by=('last_name', 'first_name'))
  
  # create lookup dict for driver_id's
  g.driver_dict = {}
  for driver in g.driver_list:
    g.driver_dict[driver['driver_id']] = driver

  return render_template('admin_scores.html')

#######################################

@app.route('/season', methods=['GET','POST'])
def season_page():
  db = get_db()
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  
  action = request.form.get('action')
  
  # FIXME TODO
  # ...

  return render_template('admin_season.html')

#######################################

@app.route('/export_results')
def export_results_page():
  db = get_db()
  g.rules = get_rules(db)

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.select_one('events', event_id=g.active_event_id)
  if g.active_event is None:
    flash("No active event!", F_ERROR)
    return redirect(url_for('events_page'))
  
  output_format = request.form.get('format', 'csv')

  # sort entries into car class
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
  for entry in g.driver_entry_list:
    g.entry_run_list[entry['entry_id']] = db.run_list(entry_id=entry['entry_id'], state_filter=('scored',), limit=g.rules.max_runs)

  output = StringIO()

  writer = csv.writer(output)

  row = []
  row.append('car_class')
  row.append('car_number')
  row.append('first_name')
  row.append('last_name')
  row.append('car_year')
  row.append('car_make')
  row.append('car_model')
  row.append('car_color')
  
  for i in range(g.rules.max_runs):
    row.append('raw[%d]' % (i+1))
    row.append('C[%d]' % (i+1))
    row.append('G[%d]' % (i+1))
    row.append('total[%d]' % (i+1))

  row.append('event_penalties')
  row.append('event_total_time')

  writer.writerow(row)

  for car_class in g.rules.car_class_list:
    if car_class in g.class_entry_list:
      for entry in g.class_entry_list[car_class]:
        row = []
        row.append(entry['car_class'])
        row.append(entry['car_number'])
        first_name = entry['alt_name'] if entry['alt_name'] else entry['first_name']
        row.append(first_name)
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
  response.headers['Content-Disposition'] = 'attachment; filename="%s_results.csv"' % g.active_event['event_date']
  response.mimetype = 'text/csv'

  return response

#######################################


@app.route('/debug/registry', methods=['GET','POST'])
def debug_registry_page():
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

  reg_list = db.reg_list(request.args.get('all',False))

  # query settings
  return render_template('admin_debug_registry.html', reg_list=reg_list)


#######################################


@app.route('/debug')
def debug_page():
  db = get_db()
  output = "Nothing to see here!"
  return output


#######################################


if __name__ == '__main__':
  # start dev server at localhost:8020
  app.run(host="127.0.0.1", port=8020, debug=True)

