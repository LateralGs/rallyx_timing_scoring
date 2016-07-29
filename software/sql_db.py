import sqlite3
import threading
import logging
from util import format_time, time_cmp

#######################################

# this number should match the schema_versions/version_NNN.sql file name used to init the db
SCHEMA_VERSION = 2

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
    except sqlite3.Error:
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
  def init_schema(self):
    cur = self.con.cursor()
    with open("schema_versions/version_%03d.sql" % SCHEMA_VERSION) as sql_file:
      cur.executescript(sql_file.read())
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
    self.columns['penalties'] = self.table_columns('penalties')
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

  def penalty_insert(self, entry_id, time_ms, penalty_note=None):
    rowid = self.con.execute("INSERT INTO penalties (entry_id, time_ms, penalty_note) VALUES (?,?,?)", (entry_id, time_ms, penalty_note)).lastrowid
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
  
  def penalty_delete(self, penalty_id):
    self.con.execute("DELETE FROM penalties WHERE penalty_id=?", (penalty_id,))
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

  def penalty_update(self, penalty_id, **kwargs):
    sql_keys = []
    sql_values = []
    for key,value in kwargs.items():
      if key in self.columns['penalties'] and key != 'penalty_id':
        sql_keys.append(key)
        sql_values.append(value)
      else:
        self.log.warning("invalid key: %r", key)
    self.con.execute("UPDATE penalties SET %s WHERE penalty_id=?" % ",".join(map(lambda k: "%s=?" % k, sql_keys)), sql_values + [penalty_id])
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

  def penalty_get(self, penalty_id):
    return self.con.execute("SELECT * FROM penalties WHERE penalty_id=? LIMIT 1", (penalty_id,)).fetchone()

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
  
  def penalty_list(self, event_id):
    return self.con.execute("SELECT penalties.* FROM penalties, entries WHERE penalties.entry_id=entries.entry_id AND entries.event_id=?", (event_id,)).fetchall()

  def entry_penalty_list(self, entry_id):
    return self.con.execute("SELECT * FROM penalties WHERE entry_id=?", (entry_id,)).fetchall()

  def entry_penalty_total(self, entry_id):
    return int(self.con.execute("SELECT total(time_ms) FROM penalties WHERE entry_id=?", (entry_id,)).fetchone()[0])

  def event_list(self):
    return self.con.execute("SELECT * FROM events ORDER BY event_date DESC").fetchall()

  def driver_by_entry(self, entry_id):
    return self.con.execute("SELECT drivers.* FROM drivers, event_entries WHERE driver.driver_id=event_entries.driver_id AND event_entries.entry_id=? LIMIT 1", (entry_id,)).fetchone()

  def entries_by_card(self, event_id, card_number):
    return self.con.execute("SELECT entries.* FROM entries, drivers WHERE entries.driver_id=drivers.driver_id AND entries.event_id=? AND drivers.card_number=?", (event_id, card_number)).fetchall()

  def driver_by_card(self, card_number):
    return self.con.execute("SELECT * FROM drivers WHERE card_number=? LIMIT 1", (card_number,)).fetchone()
  
  def entries_session_update(self, event_id, car_class, class_session):
    self.con.execute("UPDATE entries SET race_session=? WHERE car_class=? AND event_id=?", (class_session, car_class, event_id))
    self.con.commit()

  def run_started(self, event_id, time_ms, entry_id):
    rowid = self.con.execute("INSERT INTO runs (event_id, start_time_ms, entry_id, state) VALUES (?,?,?,'started')", (event_id, time_ms, entry_id)).lastrowid
    self.con.commit()
    return rowid

  def run_finished(self, event_id, time_ms):
    # TODO FIXME there needs to be better transaction control here?
    cur = self.con.cursor()
    row = cur.execute("SELECT run_id FROM runs WHERE event_id=? AND NOT start_time_ms ISNULL AND start_time_ms > 0 AND start_time_ms <= ? AND state='started' ORDER BY run_id ASC LIMIT 1", (event_id, time_ms)).fetchone()
    if row is None:
      return None
    cur.execute("UPDATE runs SET finish_time_ms=?, state='finished' WHERE run_id = ?", (time_ms, row['run_id']))
    self.con.commit()
    return row['run_id']

  def run_split_1(self, event_id, time_ms):
    pass # TODO like run_finished find next run to update split 1

  def run_split_2(self, event_id, time_ms):
    pass # TODO like run_finished find next run to update split 2

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


#######################################
#######################################



