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

@request_started.connect_via(app)
def request_started_signal(sender, **extra):
  pass

#######################################

@app.route('/')
def index_page():
  db = get_db()
  db.reg_inc('.pc_index')
  # nothing to do, static page for instructions
  return render_template('admin_index.html')

@app.route('/events', methods=['GET','POST'])
def events_page():
  db = get_db()
  db.reg_inc('.pc_events')

  action = request.form.get('action')

  if action == 'activate':
    event_id = request.form.get('event_id')
    if db.event_exists(event_id):
      db.reg_set('active_event_id', event_id)
      flash("Set active event to %r" % event_id)
    else:
      flash("Invalid event_id")
    return redirect(url_for('events_page'));

  elif action == 'update':
    event_id = request.form.get('event_id')
    if not db.event_exists(event_id):
      flash("Invalid event id")
      return redirect(url_for('events_page'))
    event_data = {}
    for key in db.columns['events']:
      if key in ['event_id']:
        continue # ignore
      elif key in request.form:
        event_data[key] = request.form.get(key)
    db.event_update(event_id, **event_data)
    flash("Event changes saved")
    return redirect(url_for('events_page'))

  elif action == 'insert':
    event_data = {}
    for key in db.columns['events']:
      if key in ['event_id']:
        continue # ignore
      elif key in request.form:
        event_data[key] = request.form.get(key)
    event_id = db.event_insert(**event_data)
    flash("Added new event [%r]" % event_id)
    return redirect(url_for('events_page'))

  elif action == 'delete':
    if request.form.get('confirm_delete') == 'do_it':
      event_id = request.form.get('event_id')
      if db.event_exists(event_id):
        if db.reg_get('active_event_id') == event_id:
          db.reg_set('active_event_id',None)
        db.event_delete(event_id)
        flash("Event deleted")
      else:
        flash("Invalid event_id for delete operation.")
    else:
      flash("Delete ignored, no confirmation")
    return redirect(url_for('events_page'))

  elif action is not None:
    flash("Invalid form action %r" % action)
    return redirect(url_for('events_page'))

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.event_get(g.active_event_id)
  g.event_list = db.event_list()
  g.default_date = datetime.date.today().isoformat()
  
  return render_template('admin_events.html')

#######################################

@app.route('/timing', methods=['GET','POST'])
def timing_page():
  db = get_db()
  db.reg_inc('.pc_timing')

  active_event_id = db.reg_get_int('active_event_id')
  logging.debug("active_event_id = %r", active_event_id)
  if not db.event_exists(active_event_id):
    flash("No active event!")
    return redirect(url_for('events_page'))

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
    db.reg_set('next_entry_id',request.form.get('next'))
    return redirect(url_for('timing_page'))

  elif action == 'clear_next':
    db.reg_set('next_entry_id', None)
    return redirect(url_for('timing_page'))

  elif action == 'set_filter':
    session['entry_filter'] = request.form.get('entry_filter')
    session['started_filter'] = bool(request.form.get('started_filter'))
    session['finished_filter'] = bool(request.form.get('finished_filter'))
    session['scored_filter'] = bool(request.form.get('scored_filter'))
    session['tossout_filter'] = bool(request.form.get('tossout_filter'))

    if session['entry_filter'] not in (None, 'all', 'noassign'):
      try:
        session['entry_filter'] = int(session['entry_filter'])
      except ValueError:
        flash("Invalid driver filter")
        session['entry_filter'] = None

    return redirect(url_for('timing_page'))

  elif action == 'reset_filter':
    session['entry_filter'] = None
    session['started_filter'] = True
    session['finished_filter'] = True
    session['scored_filter'] = True
    session['tossout_filter'] = True
    return redirect(url_for('timing_page'))

  elif action == 'set_max_runs':
    try:
      max_runs = int(request.form.get('max_runs', db.reg_get('max_runs', app.config['DEFAULT_MAX_RUNS'])))
    except ValueError:
      flash("Invalid max runs")
    else:
      db.reg_set("max_runs", max(app.config['MIN_RUNS'], max_runs))
    return redirect(url_for('timing_page'))

  elif action == 'update' or action == 'update_print':
    run_id = request.form.get('run_id')
    if not db.run_exists(run_id):
      flash("Invalid run id")
      return redirect(url_for('timing_page'))
    run_data = {}
    for key in db.columns['runs'] + ['start_time','finish_time']:
      if key in ['run_id']:
        continue # ignore
      elif key == 'start_time':
        start_time_ms = parse_time(request.form.get(key))
        if start_time_ms is not None:
          run_data['start_time_ms'] = start_time_ms
        else:
          flash("Invalid start time, start time not changed.")
      elif key == 'finish_time' and request.form.get('old_state') != 'started':
        # prevent user from clobbering finish time
        # if changing to started clear finish time
        if request.form.get('state') == 'started':
          run_data['finish_time_ms'] = None
        else:
          run_data['finish_time_ms'] = parse_time(request.form.get(key))
      elif key == 'state' and request.form.get('state') == request.form.get('old_state'):
        pass # ignore setting state so we dont clobber a finish
      elif key in request.form:
        run_data[key] = clean_str(request.form.get(key))

    if run_data.get('start_time_ms') == 0 and request.form.get('state') == 'started':
      run_data['state'] = 'finished'

    logging.debug(run_data)
    db.run_update(run_id, **run_data)
    flash("Run changes saved")
    db.run_recalc(run_id)
    flash("Run recalc")
    if 'entry_id' in run_data and run_data['entry_id'] is not None:
      db.entry_recalc(run_data['entry_id'], app.config['MIN_RUNS'],db.reg_get_int('max_runs', app.config['DEFAULT_MAX_RUNS']), app.config['DROP_RUNS'])
      flash("Entry recalc")

    if action == 'update_print':
      run = db.run_get(run_id)
      if run['state'] != 'scored':
        flash("No label printed, run is not in the scored state!", 'warning')
      elif run['entry_id'] is None:
        print_label("No label printed, entry not assigned to run!", 'warning')
      else:
        entry = db.entry_driver_get(run['entry_id'])

        if entry['alt_name']:
          entry_name = entry['first_name'] + ' (' + entry['alt_name'] + ') ' + entry['last_name']
        else:
          entry_name = entry['first_name'] + ' ' + entry['last_name']
          
        label_text = " %2s %-3s %-24s %4s" % (entry['car_class'], entry['car_number'], entry_name, run['run_count'])
        label_text += "\r\n"
        cones = '-' if run['cones'] is None else run['cones']
        gates = '-' if run['gates'] is None else run['gates']
        label_text += " %12s %4s %4s %12s" % ( run['raw_time'], cones, gates, run['total_time'] )
        label_text += "\r\n"
        label_text += " %12s %4s %4s %12s" % ("Raw", "C", "G", "Score")
        label_text += "\r\n\r\n"
        label_text += "                 Total: %12s" % entry['event_time']

        print_label(app.config['PRINTER_NAME'], label_text)
        flash("Label Printed")

    return redirect(url_for('timing_page'))

  elif action == 'insert':
    run_data = {}
    for key in db.columns['runs']:
      if key in ['run_id']:
        continue # ignore
      elif key in request.form:
        run_data[key] = clean_str(request.form.get(key))
    run_id = db.run_insert(**run_data)
    db.run_recalc(run_id)
    flash("Added new run [%r]" % run_id)
    return redirect(url_for('timing_page'))

  elif action == 'print':
    flash("Print label: FIXME")
    return redirect(url_for('timing_page'))

  elif action is not None:
    flash("Invalid form action %r" % action)
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

  state_filter = []
  if session['started_filter']:
    state_filter += ['started']
  if session['finished_filter']:
    state_filter += ['finished']
  if session['scored_filter']:
    state_filter += ['scored']
  if session['tossout_filter']:
    state_filter += ['tossout']

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.event_get(g.active_event_id)
  g.max_time_events = db.reg_get_int('max_time_events', app.config['DEFAULT_MAX_TIME_EVENTS'])
  g.time_list = db.time_list(g.active_event_id, session['hide_invalid_times'], g.max_time_events)
  g.run_list = db.run_list(event_id=g.active_event_id, entry_id=session['entry_filter'], state_filter=state_filter, rev_sort=True)
  g.entry_driver_list = db.entry_driver_list(g.active_event_id)
  g.cars_started = db.run_count(g.active_event_id, state_filter=('started',))
  g.cars_finished = db.run_count(g.active_event_id, state_filter=('finished',))
  g.max_runs = db.reg_get("max_runs", app.config['DEFAULT_MAX_RUNS'])
  g.disable_start = db.reg_get_int('disable_start', 0)
  g.disable_finish = db.reg_get_int('disable_finish', 0)
  g.next_entry_id = db.reg_get_int('next_entry_id')
  g.next_entry_driver = db.entry_driver_get(g.next_entry_id)
  g.next_entry_run_count = db.run_count(g.active_event_id, g.next_entry_id, state_filter=('started','finished','scored'))
  g.scanner_status = db.reg_get('scanner_status')
  g.tag_heuer_status = db.reg_get('tag_heuer_status')
  g.rallyx_timer_status = db.reg_get('rallyx_timer_status')
  g.rfid_status = db.reg_get('rfid_status')
  g.hardware_ok = bool(time() - db.reg_get_float('hardware_watchdog', 0) < 3)
  g.start_ready = g.hardware_ok and (g.tag_heuer_status == 'Open' or g.rallyx_timer_status == 'Open') and not g.disable_start
  g.finish_ready = g.hardware_ok and (g.tag_heuer_status == 'Open' or g.rallyx_timer_status == 'Open') and not g.disable_finish

  return render_template('admin_timing.html')

#######################################

@app.route('/entries', methods=['GET','POST'])
def entries_page():
  db = get_db()
  db.reg_inc('.pc_entries')

  active_event_id = db.reg_get_int('active_event_id')
  if not db.event_exists(active_event_id):
    flash("No active event!")
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  if action == 'delete':
    if request.form.get('confirm_delete') == 'do_it':
      entry_id = request.form.get('entry_id')
      if db.entry_exists(entry_id):
        db.entry_delete(entry_id)
        flash("Entry deleted")
      else:
        flash("Invalid entry_id for delete operation.")
    else:
      flash("Delete ignored, no confirmation")
    return redirect(url_for('entries_page'))

  elif action == 'print':
    entry_id = request.form.get('entry_id')
    if entry_id is not None:
      entry = db.entry_driver_get(entry_id)

      if entry['alt_name']:
        entry_name = entry['first_name'] + ' (' + entry['alt_name'] + ') ' + entry['last_name']
      else:
        entry_name = entry['first_name'] + ' ' + entry['last_name']
        
      label_text = " %2s %-3s" % (entry['car_class'], entry['car_number'])
      label_text += "\r\n"
      label_text += " " + entry_name

      print_label(app.config['PRINTER_NAME'], label_text, lpi=3)
      flash("Label Printed")
      flash('<a href="#%s">Goto Entry</a>' % entry_id, 'safe')
    else:
      flash("No label printed, entry_id is None!", "warning")
    return redirect(url_for('entries_page'))

  elif action == 'insert':
    entry_data = {}
    for key in db.columns['entries']:
      if key in ['entry_id']:
        continue # ignore
      elif key == 'rfid_number':
        # parse the number to validate and remove leading zeros
        entry_data[key] = parse_int(request.form.get(key))
      elif key in request.form:
        entry_data[key] = clean_str(request.form.get(key))
    if 'driver_id' not in entry_data or entry_data['driver_id'] is None:
      flash("Invalid driver for new entry, no entry created.", 'error')
    elif 'car_class' not in entry_data or entry_data['car_class'] not in app.config['CAR_CLASSES']:
      flash("Invalid car class for new entry, no entry created.", 'error')
    else:
      if db.entry_by_driver(active_event_id, entry_data['driver_id']):
        flash("Entry already exists for driver! Creating new entry anyways.", 'warning')
      entry_id = db.entry_insert(**entry_data)
      flash("Added new entry [%r]" % entry_id)
    return redirect(url_for('entries_page'))

  elif action == 'update':
    entry_id = request.form.get('entry_id')
    if not db.entry_exists(entry_id):
      flash("Invalid entry id")
      return redirect(url_for('entries_page'))
    entry_data = {}
    for key in db.columns['entries']:
      if key in ['entry_id']:
        continue # ignore
      elif key == 'rfid_number':
        # parse the number to validate and remove leading zeros
        entry_data[key] = parse_int(request.form.get(key))
      elif key in request.form:
        entry_data[key] = clean_str(request.form.get(key))
    db.entry_update(entry_id, **entry_data)
    flash("Entry changes saved")
    return redirect(url_for('entries_page'))

  elif action is not None:
    flash("Invalid form action %r" % action)
    return redirect(url_for('entries_page'))

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.event_get(g.active_event_id)
  g.entry_driver_list = db.entry_driver_list(g.active_event_id)
  g.driver_list = db.driver_list()
  return render_template('admin_entries.html')

#######################################

@app.route('/drivers', methods=['GET','POST'])
def drivers_page():
  db = get_db()
  db.reg_inc('.pc_drivers')

  active_event_id = db.reg_get_int('active_event_id')
  if not db.event_exists(active_event_id):
    flash("No active event!")
    return redirect(url_for('events_page'))

  action = request.form.get('action')

  if action == 'delete':
    if request.form.get('confirm_delete') == 'do_it':
      driver_id = request.form.get('driver_id')
      if db.driver_exists(driver_id):
        db.driver_delete(driver_id)
        flash("Driver deleted")
      else:
        flash("Invalid driver_id for delete operation.")
    else:
      flash("Delete ignored, no confirmation")
    return redirect(url_for('drivers_page'))

  elif action == 'insert':
    driver_data = {}
    for key in db.columns['drivers']:
      if key in ['driver_id']:
        continue # ignore
      elif key in request.form:
        driver_data[key] = clean_str(request.form.get(key))
    driver_id = db.driver_insert(**driver_data)
    flash("Added new driver [%r]" % driver_id)
    return redirect(url_for('drivers_page'))

  elif action == 'update':
    driver_id = request.form.get('driver_id')
    if not db.driver_exists(driver_id):
      flash("Invalid driver id")
      return redirect(url_for('drivers_page'))
    driver_data = {}
    for key in db.columns['drivers']:
      if key in ['driver_id']:
        continue # ignore
      elif key in request.form:
        driver_data[key] = clean_str(request.form.get(key))
    db.driver_update(driver_id, **driver_data)
    flash("Driver changes saved")
    return redirect(url_for('drivers_page'))
  
  elif action is not None:
    flash("Unkown form action %r" % action)
    return redirect(url_for('drivers_page'))

  g.active_event_id = db.reg_get_int('active_event_id')
  g.active_event = db.event_get(g.active_event_id)
  g.driver_list = db.driver_list()
  return render_template('admin_drivers.html')

#######################################

@app.route('/scores')
def scores_page():
  db = get_db()
  db.reg_inc('.pc_scores')

  g.active_event_id = db.reg_get_int('active_event_id')
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

  return render_template('admin_scores.html')

#######################################

@app.route('/next_entry')
def next_entry_json():
  db = get_db()
  db.reg_inc('.pc_next_entry')
  next_entry = db.reg_get('next_entry_id')
  if next_entry is not None:
    return jsonify(next_entry)
  else:
    return jsonify()

#######################################

@app.route('/debug/registry', methods=['GET','POST'])
def debug_registry_page():
  db = get_db()
  db.reg_inc('.pc_debug_registry')
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
  return render_template('debug_registry.html', reg_list=reg_list)

#######################################

@app.route('/debug')
def debug_page():
  db = get_db()
  db.reg_inc('.pc_debug')

  output = "<h3>Threads:</h3>"
  for t in threading.enumerate():
    output += t.name + "<br/>"
  output += "<h3>Page Counts:</h3>"
  output += "index = %r<br/>" % db.reg_get('.pc_index', 0)
  output += "settings = %r<br/>" % db.reg_get('.pc_settings', 0)
  output += "drivers = %r<br/>" % db.reg_get('.pc_drivers', 0)
  output += "edit_driver = %r<br/>" % db.reg_get('.pc_edit_driver', 0)
  output += "next_driver = %r<br/>" % db.reg_get('.pc_next_driver', 0)
  output += "scanner_data = %r<br/>" % db.reg_get('.pc_scanner_data', 0)
  return output

#######################################

if __name__ == '__main__':
  # start dev server at localhost:8020
  app.run(host="127.0.0.1", port=8020, debug=True)

