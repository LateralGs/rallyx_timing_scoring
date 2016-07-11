import sqlite3
import threading
import logging
from util import format_time, time_cmp

# any schema change that requires a migration should increment the schema version
# A coresponding X to Y migration function should be created to update between consecutive verions
SCHEMA_VERSION = 1

# global key/value data, config data, state, etc.
# this table should never change its definition
DROP_REGISTRY_TABLE = "DROP TABLE IF EXISTS registry;"
CREATE_REGISTRY_TABLE = """
    CREATE TABLE IF NOT EXISTS registry (
      key   TEXT PRIMARY KEY NOT NULL,
      value TEXT
    );
"""

# driver info
DROP_DRIVERS_TABLE = "DROP TABLE IF EXISTS drivers;"
CREATE_DRIVERS_TABLE = """
    CREATE TABLE IF NOT EXISTS drivers (
      driver_id       INTEGER PRIMARY KEY,
      first_name      TEXT,
      last_name       TEXT,
      alt_name        TEXT,
      msreg_number    TEXT,
      scca_number     TEXT,
      license_number  TEXT,
      addr_line_1     TEXT,
      addr_line_2     TEXT,
      addr_city       TEXT,
      addr_state      TEXT,
      addr_zip        TEXT,
      phone           TEXT,
      email           TEXT,
      license_data    TEXT, -- decoded data from barcode on drivers license
      driver_note     TEXT
    );
"""

# entries are drivers competing in an event
DROP_ENTRIES_TABLE = "DROP TABLE IF EXISTS entries"
CREATE_ENTRIES_TABLE = """
    CREATE TABLE IF NOT EXISTS entries (
      entry_id        INTEGER PRIMARY KEY,
      event_id        INT NOT NULL,
      driver_id       INT NOT NULL,
      rfid_number     TEXT,
      dual_driver     INT NOT NULL DEFAULT 0,
      car_year        TEXT,
      car_make        TEXT,
      car_model       TEXT,
      car_color       TEXT,
      car_number      TEXT NOT NULL DEFAULT '0',
      car_class       TEXT NOT NULL DEFAULT 'TO',
      season_points   INT NOT NULL DEFAULT 1,
      work_assign     TEXT,
      entry_note      TEXT,
      event_time_ms   INT,
      event_time      TEXT,
      scored_runs     INT NOT NULL DEFAULT 0,
      show_scores     INT NOT NULL DEFAULT 1 -- should the scores be publicly visible
    );
"""

DROP_RUNS_TABLE = "DROP TABLE IF EXISTS runs;"
CREATE_RUNS_TABLE = """
    CREATE TABLE IF NOT EXISTS runs (
      run_id          INTEGER PRIMARY KEY,
      event_id        INT NOT NULL,
      entry_id        INT,
      cones           INT,
      gates           INT,
      start_time_ms   INT,  -- 0 == DNS
      finish_time_ms  INT,  -- 0 == DNF
      state           TEXT, -- started, finished, scored, tossout
      raw_time_ms     INT,
      total_time_ms   INT,
      raw_time        TEXT,
      total_time      TEXT,
      drop_run        INT NOT NULL DEFAULT 0,
      run_count       INT,
      run_note        TEXT
    );
"""

# times from timing equipment at start/finish
DROP_TIMES_TABLE = "DROP TABLE IF EXISTS times;"
CREATE_TIMES_TABLE = """
    CREATE TABLE IF NOT EXISTS times (
      time_id       INTEGER PRIMARY KEY,
      event_id      INT,
      channel       TEXT,
      time_ms       INT,
      invalid       INT NOT NULL DEFAULT 0,
      time_note     TEXT
    );
"""

DROP_EVENTS_TABLE = "DROP TABLE IF EXISTS events;"
CREATE_EVENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS events (
      event_id      INTEGER PRIMARY KEY,
      name          TEXT,
      location      TEXT,
      organization  TEXT,
      date          TEXT, -- RFC3339 format date YYYY-MM-DD
      season        TEXT,
      national      INT DEFAULT 0,
      season_points INT DEFAULT 1,
      visible       INT DEFAULT 1, -- Is this event visible in the scoring browser
      event_note    TEXT
    );
"""

#######################################
#######################################

def db_thread_lock(func):
  def db_thread_lock_wrapper(self, *args, **kwargs):
    self.acquire()
    result = func(self, *args, **kwargs)
    self.release()
    return result
  return db_thread_lock_wrapper

def dict_factory(cursor, row):
  d = {}
  for idx, col in enumerate(cursor.description):
    d[col[0]] = row[idx]
  return d

def SchemaVersionException(Exception):
  pass

#######################################

class ScoringDatabase(object):
  def __init__(self, path=None, logger=None):
    if logger is None:
      self.log = logging.getLogger(__name__)
    else:
      self.log = logger
    self.con = None
    self.columns = {}
    self.lock = threading.RLock()
    self.open(path)

  @db_thread_lock
  def open(self, path):
    if path is None:
      return
    self.log.debug("open %r", path)
    if self.con:
      self.con.close()
    self.con = sqlite3.connect(path, check_same_thread=False)
    self.con.row_factory = sqlite3.Row
    try:
      version = self.reg_get_int(".schema_version")
    except sqlite3.OperationalError:
      self.init_schema()
    else:
      if version is None:
        self.init_schema()
      elif version != SCHEMA_VERSION:
        raise SchemaVersionException("db_file=%r, software=%r" % (version, SCHEMA_VERSION))
    self.init_columns()


  @db_thread_lock
  def close(self):
    if self.con:
      self.con.close()
      self.con = None

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    self.close()

  def acquire(self, blocking=True):
    """ Acquire thread lock on database """
    return self.lock.acquire(blocking)

  def release(self):
    """ Release thread lock on database """
    return self.lock.release()

  def commit(self):
    self.con.commit()

  def query(self, expr, *args):
    return self.con.execute(expr,args)

  def query_all(self, expr, *args):
    return self.con.execute(expr,args).fetchall()

  def query_one(self, expr, *args):
    return self.con.execute(expr,args).fetchone()

  def query_singleton(self, expr, *args):
    row = self.con.execute(expr,args).fetchone()
    return row[0] if row else None

  @db_thread_lock
  def drop_schema(self, confirm):
    cur = self.con.cursor()
    if confirm == "yes":
      cur.execute(DROP_REGISTRY_TABLE)
      cur.execute(DROP_DRIVERS_TABLE)
      cur.execute(DROP_ENTRIES_TABLE)
      cur.execute(DROP_RUNS_TABLE)
      cur.execute(DROP_TIMES_TABLE)
      cur.execute(DROP_EVENTS_TABLE)
      # add lines for dropping tables here
      # ...
    self.con.commit()

  @db_thread_lock
  def init_schema(self):
    cur = self.con.cursor()
    cur.execute(CREATE_REGISTRY_TABLE)
    cur.execute(CREATE_DRIVERS_TABLE)
    cur.execute(CREATE_ENTRIES_TABLE)
    cur.execute(CREATE_RUNS_TABLE)
    cur.execute(CREATE_TIMES_TABLE)
    cur.execute(CREATE_EVENTS_TABLE)
    # add lines for creating tables here
    # ...
    self.con.commit()

    # default registry settings
    self.reg_set_default('.schema_version', SCHEMA_VERSION)

  def init_columns(self):
    # read column names from database
    # FIXME maybe set these to be static based on constants defined?
    self.columns['registry'] = self.table_columns('registry')
    self.columns['drivers'] = self.table_columns('drivers')
    self.columns['entries'] = self.table_columns('entries')
    self.columns['runs'] = self.table_columns('runs')
    self.columns['times'] = self.table_columns('times')
    self.columns['events'] = self.table_columns('events')
    # add any new tables here
    # ...

  def table_names(self):
    return map(lambda row: row['name'], self.con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
  
  def table_columns(self, table_name):
    return map(lambda x: x[0], self.con.execute("SELECT * FROM %s LIMIT 1" % table_name).description)

  def table_sql(self, table_name):
    return map(lambda row: row['sql'], self.con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone())

  #### REGISTRY ####

  def reg_exists(self, key):
    return bool(self.con.execute("SELECT count(*) FROM registry WHERE key=?", (key,)).fetchone()[0])

  def reg_set_default(self, key, value):
    # this should not overwrite any existing registry values
    self.con.execute("INSERT OR IGNORE INTO registry (key,value) VALUES (?,?)", (key,value))
    self.con.commit()

  def reg_set(self, key, value):
    self.con.execute("INSERT OR REPLACE INTO registry (key,value) VALUES (?,?)", (key,value))
    self.con.commit()

  def reg_get(self, key, default=None):
    value = self.con.execute("SELECT value FROM registry WHERE key=?", (key,)).fetchone()
    if value is None:
      return default
    else:
      return value[0]

  def reg_get_int(self, key, default=None):
    try:
      return int(self.reg_get(key))
    except ValueError:
      return default
    except TypeError:
      return default
  
  def reg_get_float(self, key, default=None):
    try:
      return float(self.reg_get(key))
    except ValueError:
      return default
    except TypeError:
      return default

  def reg_toggle(self, key, default):
    if self.reg_exists(key):
      self.con.execute("UPDATE OR IGNORE registry SET value = NOT value WHERE key=?", (key,))
    else:
      self.con.execute("INSERT OR REPLACE INTO registry (key,value) VALUES (?,?)", (key,default))
    self.con.commit()

  def reg_inc(self, key):
    """ useful as a page counter """
    cur = self.con.cursor()
    cur.execute("UPDATE registry SET value=value+1 WHERE key=?", (key,))
    if cur.rowcount <= 0:
      cur.execute("INSERT OR REPLACE INTO registry (key,value) VALUES (?,?)", (key,1))
    self.con.commit()

  def reg_keys(self, hidden=False):
    if hidden:
      return map(lambda row: row[0], self.con.execute("SELECT key FROM registry").fetchall())
    else:
      return map(lambda row: row[0], self.con.execute("SELECT key FROM registry WHERE key NOT LIKE '.%'").fetchall())

  def reg_dict(self, hidden=False):
    result = {}
    if hidden:
      for row in self.con.execute("SELECT key, value FROM registry").fetchall():
        result[row['key']] = row['value']
    else:
      for row in self.con.execute("SELECT key, value FROM registry WHERE key NOT LIKE '.%'").fetchall():
        result[row['key']] = row['value']
    return result

  def reg_list(self, hidden=False):
    if hidden:
      return self.con.execute("SELECT key, value FROM registry").fetchall()
    else:
      return self.con.execute("SELECT key, value FROM registry WHERE key NOT LIKE '.%'").fetchall()

  #### INSERT ####

  def driver_insert(self, **kwargs):
    sql_keys = []
    sql_values = []
    self.log.debug(kwargs)
    for key,value in kwargs.items():
      if key in self.columns['drivers'] and key != 'driver_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    sql = "INSERT INTO drivers (%s) VALUES (%s)" % (",".join(sql_keys), ",".join(['?']*len(sql_values)))
    self.log.debug(sql)
    driver_id = self.con.execute(sql, sql_values).lastrowid
    self.con.commit()
    return driver_id

  def entry_insert(self, event_id, driver_id, **kwargs):
    sql_keys = ['event_id', 'driver_id']
    sql_values = [event_id, driver_id]
    self.log.debug(kwargs)
    for key,value in kwargs.items():
      if key in self.columns['entries'] and key != 'entry_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    sql = "INSERT INTO entries (%s) VALUES (%s)" % (",".join(sql_keys), ",".join(['?']*len(sql_values)))
    self.log.debug(sql)
    entry_id = self.con.execute(sql, sql_values).lastrowid
    self.con.commit()
    return entry_id

  def event_insert(self, **kwargs):
    sql_keys = []
    sql_values = []
    self.log.debug(kwargs)
    for key,value in kwargs.items():
      if key in self.columns['events'] and key != 'event_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    sql = "INSERT INTO events (%s) VALUES (%s)" % (",".join(sql_keys), ",".join(['?']*len(sql_values)))
    self.log.debug(sql)
    event_id = self.con.execute(sql, sql_values).lastrowid
    self.con.commit()
    return event_id
  
  def run_insert(self, event_id, **kwargs):
    sql_keys = ['event_id']
    sql_values = [event_id]
    self.log.debug(kwargs)
    for key,value in kwargs.items():
      if key in self.columns['runs'] and key != 'run_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    sql = "INSERT INTO runs (%s) VALUES (%s)" % (",".join(sql_keys), ",".join(['?']*len(sql_values)))
    self.log.debug(sql)
    run_id = self.con.execute(sql, sql_values).lastrowid
    self.con.commit()
    return run_id

  def time_insert(self, event_id, channel, time_ms, invalid=False, note=None):
    rowid = self.con.execute("INSERT INTO times (event_id, channel, time_ms, invalid, time_note) VALUES (?,?,?,?,?)", (event_id, channel, time_ms, invalid, note)).lastrowid
    self.con.commit()
    return rowid

  #### DELETE ####
  
  def driver_delete(self, driver_id):
    self.con.execute("DELETE FROM drivers WHERE driver_id=?", (driver_id,))
    for entry in self.con.execute("SELECT entry_id FROM entries WHERE driver_id=?", (driver_id,)).fetchall():
      self.con.execute("UPDATE runs SET entry_id=NULL WHERE entry_id=?", (entry_id,))
      self.con.execute("DELETE FROM entries WHERE entry_id=?", (entry_id,))
    self.con.commit()
  
  def event_delete(self, event_id):
    self.con.execute("DELETE FROM events WHERE event_id=?", (event_id,))
    self.con.execute("DELETE FROM entries WHERE event_id=?", (event_id,))
    self.con.execute("DELETE FROM runs WHERE event_id=?", (event_id,))
    self.con.execute("DELETE FROM times WHERE event_id=?", (event_id,))
    self.con.commit()

  def entry_delete(self, entry_id):
    self.con.execute("DELETE FROM entries WHERE entry_id=?", (entry_id,))
    self.con.execute("UPDATE runs SET entry_id=NULL WHERE entry_id=?", (entry_id,))
    self.con.commit()

  def run_delete(self, run_id):
    self.con.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
    self.con.commit()

  def time_delete(self, time_id):
    self.con.execute("DELETE FROM times WHERE time_id=?", (time_id,))
    self.con.commit()

  #### UPDATE ####
  
  def driver_update(self, driver_id, **kwargs):
    sql_keys = []
    sql_values = []
    for key,value in kwargs.items():
      if key in self.columns['drivers'] and key != 'driver_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    self.con.execute("UPDATE drivers SET %s WHERE driver_id=?" % ",".join(map(lambda k: "%s=?" % k, sql_keys)), sql_values + [driver_id])
    self.con.commit()

  def entry_update(self, entry_id, **kwargs):
    self.log.debug(entry_id)
    self.log.debug(kwargs)
    sql_keys = []
    sql_values = []
    for key,value in kwargs.items():
      if key in self.columns['entries'] and key != 'entry_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    self.con.execute("UPDATE entries SET %s WHERE entry_id=?" % ",".join(map(lambda k: "%s=?" % k, sql_keys)), sql_values + [entry_id])
    self.con.commit()

  def run_update(self, run_id, **kwargs):
    sql_keys = []
    sql_values = []
    for key,value in kwargs.items():
      if key in self.columns['runs'] and key != 'run_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    self.con.execute("UPDATE runs SET %s WHERE run_id=?" % ",".join(map(lambda k: "%s=?" % k, sql_keys)), sql_values + [run_id])
    self.con.commit()

  def event_update(self, event_id, **kwargs):
    sql_keys = []
    sql_values = []
    for key,value in kwargs.items():
      if key in self.columns['events'] and key != 'event_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    self.con.execute("UPDATE events SET %s WHERE event_id=?" % ",".join(map(lambda k: "%s=?" % k, sql_keys)), sql_values + [event_id])
    self.con.commit()

  def time_update(self, time_id, **kwargs):
    sql_keys = []
    sql_values = []
    for key,value in kwargs.items():
      if key in self.columns['times'] and key != 'time_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    self.con.execute("UPDATE times SET %s WHERE time_id=?" % ",".join(map(lambda k: "%s=?" % k, sql_keys)), sql_values + [time_id])
    self.con.commit()

  #### QUERY ####
  
  def driver_exists(self, driver_id):
    return bool(self.con.execute("SELECT count(*) FROM drivers WHERE driver_id=?", (driver_id,)).fetchone()[0])
  
  def entry_exists(self, entry_id):
    return bool(self.con.execute("SELECT count(*) FROM entries WHERE entry_id=?", (entry_id,)).fetchone()[0])

  def run_exists(self, run_id):
    return bool(self.con.execute("SELECT count(*) FROM runs WHERE run_id=?", (run_id,)).fetchone()[0])

  def event_exists(self, event_id):
    return bool(self.con.execute("SELECT count(*) FROM events WHERE event_id=?", (event_id,)).fetchone()[0])

  def time_exists(self, time_id):
    return bool(self.con.execute("SELECT count(*) FROM times WHERE time_id=?", (time_id,)).fetchone()[0])

  def driver_get(self, driver_id):
    return self.con.execute("SELECT * FROM drivers WHERE driver_id=? LIMIT 1", (driver_id,)).fetchone()

  def entry_get(self, entry_id):
    return self.con.execute("SELECT * FROM entries WHERE entry_id=? LIMIT 1", (entry_id,)).fetchone()

  def event_get(self, event_id):
    return self.con.execute("SELECT * FROM events WHERE event_id=? LIMIT 1", (event_id,)).fetchone()
  
  def run_get(self, run_id):
    return self.con.execute("SELECT * FROM runs WHERE run_id=? LIMIT 1", (run_id,)).fetchone()
  
  def time_get(self, time_id):
    return self.con.execute("SELECT * FROM times WHERE time_id=? LIMIT 1", (time_id,)).fetchone()

  def driver_by_msreg(self, msreg_number):
    return self.con.execute("SELECT * FROM drivers WHERE msreg_number=? LIMIT 1", (msreg_number,)).fetchone()

  def driver_by_card_number(self, card_number):
    return self.con.execute("SELECT * FROM drivers WHERE card_number=? LIMIT 1", (card_number,)).fetchone()

  def entry_by_driver(self, event_id, driver_id):
    return self.con.execute("SELECT * FROM entries WHERE event_id=? AND driver_id=? LIMIT 1", (event_id, driver_id)).fetchone()

  def entry_check_driver(self, entry_id, driver_id):
    return self.con.execute("SELECT count(*) FROM entries WHERE entry_id=? AND driver_id=? LIMIT 1", (entry_id, driver_id)).fetchone()[0]

  def entry_driver_get(self, entry_id):
    return self.con.execute("SELECT * FROM entries, drivers WHERE entries.driver_id=drivers.driver_id AND entry_id=? LIMIT 1", (entry_id,)).fetchone()

  def driver_list(self):
    return self.con.execute("SELECT * FROM drivers ORDER BY last_name, first_name").fetchall()

  def entry_list(self, event_id):
    return self.con.execute("SELECT * FROM entries WHERE event_id=?", (event_id,)).fetchall()
  
  def entry_id_list(self, event_id):
    return self.con.execute("SELECT entry_id FROM entries WHERE event_id=?", (event_id,)).fetchall()
  
  def entry_driver_list(self, event_id):
    return self.con.execute("SELECT * FROM entries, drivers WHERE entries.driver_id=drivers.driver_id AND event_id=? ORDER BY entries.car_class, entries.car_number, drivers.last_name", (event_id,)).fetchall()

  def run_list(self, event_id=None, entry_id=None, state_filter=None, limit=None, offset=None, rev_sort=False):
    sql = "SELECT * FROM runs WHERE 1 "
    args = []

    if event_id is None and entry_id is None:
      raise Exception("Oops! missing event_id or entry_id")
    
    if event_id is not None:
      sql += " AND event_id=? "
      args += [event_id]

    if entry_id is None or entry_id == 'all':
      pass # no filter, all results
    elif entry_id == 'noassign' or entry_id == 'null':
      sql += " AND entry_id ISNULL "
    else:
      sql += " AND entry_id=? "
      args += [entry_id]

    if state_filter and len(state_filter) > 0:
      sql += " AND state in (" + ','.join('?'*len(state_filter)) + ") "
      args += state_filter

    if rev_sort:
      sql += " ORDER BY run_id DESC "
    else:
      sql += " ORDER BY run_id ASC "

    if limit:
      sql += " LIMIT %d " % limit
      if offset:
        sql += " OFFSET %d " % offset

    self.log.debug(sql)
    self.log.debug(args)

    return self.con.execute(sql, args).fetchall()


  def time_list(self, event_id, hide_invalid=False, limit=100):
    if hide_invalid:
      return self.con.execute("SELECT * FROM times WHERE event_id=? AND NOT invalid ORDER BY rowid DESC LIMIT ?", (event_id, limit)).fetchall()
    else:
      return self.con.execute("SELECT * FROM times WHERE event_id=? ORDER BY rowid DESC LIMIT ?", (event_id, limit)).fetchall()

  def event_list(self):
    return self.con.execute("SELECT * FROM events ORDER BY date DESC").fetchall()

  def driver_by_entry(self, entry_id):
    return self.con.execute("SELECT drivers.* FROM drivers, event_entries WHERE driver.driver_id=event_entries.driver_id AND event_entries.entry_id=? LIMIT 1", (entry_id,)).fetchone()

  def entry_by_rfid(self, event_id, rfid_number):
    return self.con.execute("SELECT * FROM entries WHERE event_id=? AND rfid_number=? LIMIT 1", (event_id, rfid_number)).fetchone()

  def run_started(self, event_id, time_ms, entry_id):
    rowid = self.con.execute("INSERT INTO runs (event_id, start_time_ms, entry_id, state) VALUES (?,?,?,'started')", (event_id, time_ms, entry_id)).lastrowid
    self.con.commit()
    return rowid

  def run_finished(self, event_id, time_ms):
    # TODO FIXME there needs to be better transaction control here
    cur = self.con.cursor()
    row = cur.execute("SELECT run_id FROM runs WHERE event_id=? AND NOT start_time_ms ISNULL AND start_time_ms > 0 AND start_time_ms <= ? AND state='started' ORDER BY run_id ASC LIMIT 1", (event_id, time_ms)).fetchone()
    if row is None:
      return None
    cur.execute("UPDATE runs SET finish_time_ms=?, state='finished' WHERE run_id = ?", (time_ms, row['run_id']))
    self.con.commit()
    return row['run_id']

  def run_count(self, event_id, entry_id=None, state_filter=None, max_run_id=None):
    sql = "SELECT count(*) FROM runs WHERE event_id=? "
    args = [event_id]
    
    if entry_id is None or entry_id == 'all':
      pass # no filter, all results
    elif entry_id == 'noassign' or entry_id == 'null':
      sql += " AND entry_id ISNULL "
    else:
      sql += " AND entry_id=? "
      args += [entry_id]

    if state_filter and len(state_filter) > 0:
      sql += " AND state in (" + ','.join('?'*len(state_filter)) + ") "
      args += state_filter

    if max_run_id:
      sql += " AND run_id<=? "
      args += [max_run_id]

    self.log.debug(sql)
    self.log.debug(args)

    return self.con.execute(sql, args).fetchone()[0]


  def run_recalc(self, run_id, cone_penalty=2, gate_penalty=10):
    run = self.run_get(run_id)
    if run is None:
      return
    raw_time = None
    total_time = None
    raw_time_ms = None
    total_time_ms = None
    run_count = None
    if run['start_time_ms'] == 0:
      raw_time = "DNS"
      total_time = "DNS"
    elif run['finish_time_ms'] == 0:
      raw_time = "DNF"
      total_time = "DNF"
    elif run['start_time_ms'] is None:
      pass
    elif run['finish_time_ms'] is None:
      pass
    elif run['finish_time_ms'] <= run['start_time_ms']:
      raw_time = "INVALID"
      total_time = "INVALID"
    else:
      total_time_ms = raw_time_ms = run['finish_time_ms'] - run['start_time_ms']
      if run['cones']:
        total_time_ms += run['cones'] * cone_penalty * 1000 # penalty is in seconds, we need milliseconds
      if run['gates']:
        total_time_ms += run['gates'] * gate_penalty * 1000 # penalty is in seconds, we need milliseconds
      raw_time = format_time(raw_time_ms)
      total_time = format_time(total_time_ms)

    if run['entry_id'] is not None:
      run_count = self.run_count(run['event_id'], run['entry_id'], state_filter=('scored','started','finished'), max_run_id=run_id)

    self.run_update(run_id, raw_time=raw_time, total_time=total_time, raw_time_ms=raw_time_ms, total_time_ms=total_time_ms, run_count=run_count)

  def entry_recalc(self, entry_id, min_runs, max_runs, max_drop):
    # calculate event_time_ms, event_time and drop runs
    entry_runs = self.run_list(entry_id=entry_id, state_filter=('scored',))
    self.log.debug(entry_runs)

    dropped_runs = []
    scored_runs = []

    # make sure we only drop if we are more than min runs
    max_drop = min(max_drop, max_runs-min_runs)

    # drop runs that are beyond max_runs
    for i in range(len(entry_runs)):
      if i >= max_runs:
        dropped_runs.append(entry_runs[i])
      else:
        scored_runs.append(entry_runs[i])

    scored_run_count = len(scored_runs)

    self.log.debug("scored: %r", scored_runs)
    self.log.debug("dropped: %r", dropped_runs)

    # sort runs then find out which runs we drop
    scored_runs.sort(cmp=time_cmp, key=lambda r: r['total_time_ms'])
    dropped_runs += scored_runs[max_runs-max_drop:]
    del scored_runs[max_runs-max_drop:]

    event_time_ms = 0
    event_time = None
    for run in scored_runs:
      if run['start_time_ms'] == 0 or run['finish_time_ms'] == 0:
        event_time_ms = None
        event_time = "DNF"
        break;
      elif run['total_time_ms']:
        event_time_ms += run['total_time_ms']
    event_time = format_time(event_time_ms)

    self.entry_update(entry_id=entry_id, event_time_ms=event_time_ms, event_time=event_time, scored_runs=scored_run_count)
    
    for run in entry_runs:
      if run in dropped_runs:
        self.run_update(run_id=run['run_id'], drop_run=1)
      else:
        self.run_update(run_id=run['run_id'], drop_run=0)



#######################################
#######################################



