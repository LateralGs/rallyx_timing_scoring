import apsw
import logging
from util import format_time, time_cmp
import types

#######################################

# this number should match the schema_versions/version_NNN.sql file name used to init the db
SCHEMA_VERSION = 4

# used as global storage for table column names
columns = {}

#######################################

def dict_row_factory(cursor, row):
  d = {}
  for idx, col in enumerate(cursor.getdescription()):
    #d[idx] = row[idx] # numerical indexing
    d[col[0]] = row[idx] # column name indexing
  return d

def SchemaVersionException(Exception):
  pass

def columns_exectrace(cursor, sql, bindings):
  global columns
  table_name = '_'
  if '--' in sql:
    table_name = sql.split("--",1)[1].strip()
  columns[table_name] = map(lambda x: x[0], cursor.getdescription())
  return True

#######################################

class ScoringDatabase(apsw.Connection):
  def __init__(self, path, logger=None):
    if logger is None:
      self.log = logging.getLogger(__name__)
    else:
      self.log = logger
    super(ScoringDatabase,self).__init__(path)
    self._context_stack = 0 # used for nesting context manager calls using 'with' stantement
    self.setbusytimeout(10000) # 10 seconds
    self.setrowtrace(dict_row_factory)
    self.check_schema()
    

  def check_schema(self):
    try:
      version = self.reg_get_int(".schema_version")
    except apsw.SQLError:
      self.init_schema()
    else:
      if version is None:
        self.init_schema()
      elif version != SCHEMA_VERSION:
        raise SchemaVersionException("db_file=%r, software=%r" % (version, SCHEMA_VERSION))

  def init_schema(self):
    cur = self.cursor()
    with open("schema_versions/version_%03d.sql" % SCHEMA_VERSION) as sql_file:
      cur.execute(sql_file.read())

    # default registry settings
    self.reg_set_default('.schema_version', SCHEMA_VERSION)

    # set database options
    cur.execute("PRAGMA journal_mode=wal")

  # change default behaviour for context handlers to use begin immediate instead of savepoint that uses defered
  def __enter__(self):
    if self._context_stack <= 0:
      self.begin_immediate()
      self._context_stack = 1
    else:
      self._context_stack += 1
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    if self._context_stack > 0:
      self._context_stack -= 1

    if self._context_stack <= 0:
      if exc_type is None:
        self.commit()
      else:
        self.rollback()

  def commit(self):
    self.cursor().execute("commit")

  def rollback(self):
    self.cursor().execute("rollback")

  def begin(self):
    self.cursor().execute("begin")

  def begin_exclusive(self):
    self.cursor().execute("begin exclusive")

  def begin_immediate(self):
    self.cursor().execute("begin immediate")

  def table_names(self):
    return map(lambda row: row['name'], self.cursor().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
  
  def table_sql(self, table_name):
    return map(lambda row: row['sql'], self.cursor().execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone())

  def table_columns(self, table_name):
    if table_name in columns:
      return columns[table_name]
    else:
      cur = self.cursor()
      cur.setexectrace(columns_exectrace)
      # hack: use a comment at the end to pass the table name to columns_exectrace
      cur.execute("SELECT * FROM " + table_name + " LIMIT 0 --" + table_name)
      return columns[table_name]

  #### SQL statement wrappers ####

  def insert(self, _table_name, **kwargs):
    keys = kwargs.keys()
    values = kwargs.values()
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (_table_name, ','.join(keys), ','.join('?' * len(keys)))
    self.cursor().execute(sql, values)
    return self.last_insert_rowid()

  def update(self, _table_name, _row_id, **kwargs):
    keys = kwargs.keys()
    values = kwargs.values()
    sql = "UPDATE %s SET %s WHERE rowid=?" % (_table_name, ', '.join(['%s=?' % k for k in keys]))
    self.cursor().execute(sql, values + [_row_id])
    return self.changes()

  def execute(self, *args, **kwargs):
    return self.cursor().execute(*args, **kwargs)

  def query_one(self, *args, **kwargs):
    return self.cursor().execute(*args, **kwargs).fetchone()
  
  def query_all(self, *args, **kwargs):
    return list(self.cursor().execute(*args, **kwargs))

  def query_single(self, *args, **kwargs):
    row = self.cursor().execute(*args, **kwargs).fetchone()
    return row.values()[0] if row else None

  def select_one(self, _table_name, _order_by=None, _offset=None, **kwargs):
    sql = "SELECT * FROM %s WHERE 1 " % _table_name
    args = []
    for key in kwargs:
      sql += " AND %s=?" % key
      args.append(kwargs[key])
    if isinstance(_order_by, types.StringTypes):
      sql += " ORDER BY %s " % _order_by
    elif isinstance(_order_by, (list,tuple)) and len(_order_by) > 0:
      sql += " ORDER BY %s " % ",".join(_order_by)
    else:
      sql += " ORDER BY rowid ASC "
    sql += " LIMIT 1"
    if _offset:
      sql += " OFFSET ? "
      args.append(_offset)
    return self.query_one(sql, args)

  def select_all(self, _table_name, _order_by=None, _limit=None, _offset=None, **kwargs):
    sql = "SELECT * FROM %s WHERE 1 " % _table_name
    args = []
    for key in kwargs:
      sql += " AND %s=?" % key
      args.append(kwargs[key])
    if isinstance(_order_by, types.StringTypes):
      sql += " ORDER BY %s " % _order_by
    elif isinstance(_order_by, (list,tuple)) and len(_order_by) > 0:
      sql += " ORDER BY %s " % ",".join(_order_by)
    else:
      sql += " ORDER BY rowid ASC "
    if _limit:
      sql += " LIMIT ? "
      args.append(_limit)
      if _offset:
        sql += " OFFSET ? "
        args.append(_offset)
    return self.query_all(sql, args)

  def count(self, _table_name, **kwargs):
    sql = "SELECT count(*) FROM %s WHERE 1 " % _table_name
    args = []
    for key in kwargs:
      sql += " AND %s=?" % key
      args.append(kwargs[key])
    return self.query_single(sql, args)

  #### REGISTRY ####

  def reg_exists(self, key):
    return bool(self.cursor().execute("SELECT count(*) as count FROM registry WHERE key=?", (key,)).fetchone()['count'])

  def reg_set_default(self, key, value):
    # this should not overwrite any existing registry values
    self.cursor().execute("INSERT OR IGNORE INTO registry (key,value) VALUES (?,?)", (key,value))

  def reg_set(self, key, value):
    self.cursor().execute("INSERT OR REPLACE INTO registry (key,value) VALUES (?,?)", (key,value))

  def reg_get(self, key, default=None):
    row = self.cursor().execute("SELECT value FROM registry WHERE key=?", (key,)).fetchone()
    if row is None:
      return default
    else:
      return row['value']

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

  def reg_toggle(self, key, default=None):
    self.cursor().execute("INSERT OR IGNORE INTO registry (key,value) VALUES (?,?); UPDATE registry SET value = NOT value WHERE key=?", (key,default,key))

  def reg_inc(self, key):
    self.cursor().execute("INSERT OR IGNORE INTO registry (key,value) VALUES (?,0); UPDATE registry SET value=value+1 WHERE key=?", (key,key))
  
  def reg_keys(self, hidden=False):
    if hidden:
      return map(lambda row: row['key'], self.cursor().execute("SELECT key FROM registry").fetchall())
    else:
      return map(lambda row: row['key'], self.cursor().execute("SELECT key FROM registry WHERE key NOT LIKE '.%'").fetchall())

  def reg_dict(self, hidden=False):
    result = {}
    if hidden:
      for row in self.cursor().execute("SELECT key, value FROM registry").fetchall():
        result[row['key']] = row['value']
    else:
      for row in self.cursor().execute("SELECT key, value FROM registry WHERE key NOT LIKE '.%'").fetchall():
        result[row['key']] = row['value']
    return result

  def reg_list(self, hidden=False):
    if hidden:
      return self.cursor().execute("SELECT key, value FROM registry").fetchall()
    else:
      return self.cursor().execute("SELECT key, value FROM registry WHERE key NOT LIKE '.%'").fetchall()

  #### OTHER ####

  def event_exists(self, event_id):
    return bool(self.cursor().execute("SELECT 1 FROM events WHERE event_id=? AND NOT deleted LIMIT 1", (event_id,)).fetchone())

  def driver_exists(self, driver_id):
    return bool(self.cursor().execute("SELECT 1 FROM drivers WHERE driver_id=? AND NOT deleted LIMIT 1", (driver_id,)).fetchone())

  def entry_exists(self, entry_id):
    return bool(self.cursor().execute("SELECT 1 FROM entries WHERE entry_id=? AND NOT deleted LIMIT 1", (entry_id,)).fetchone())

  def run_exists(self, run_id):
    return bool(self.cursor().execute("SELECT 1 FROM runs WHERE run_id=? AND NOT deleted LIMIT 1", (run_id,)).fetchone())

  def penalty_exists(self, penalty_id):
    return bool(self.cursor().execute("SELECT 1 FROM penalties WHERE penalty_id=? AND NOT deleted LIMIT 1", (penalty_id,)).fetchone())

  def driver_entry_list(self, event_id):
    return list(self.cursor().execute("SELECT * FROM driver_entries WHERE event_id=?", (event_id,)))
  
  def set_entry_recalc(self, entry_id):
    self.execute("UPDATE entries SET recalc=1 WHERE entry_id=?", (entry_id,))
    return self.changes()

  def set_event_recalc(self, event_id):
    self.execute("UPDATE entries SET recalc=1 WHERE event_id=?", (event_id,))
    # FIXME do we update runs too?
    return self.changes()

  def set_run_recalc(self, run_id):
    self.execute("UPDATE runs SET recalc=1 WHERE run_id=?", (run_id,))
    return self.changes()
  
  def entry_session_update(self, event_id, car_class, race_session):
    self.execute("UPDATE entries SET race_session=? WHERE event_id=? AND car_class=?", (race_session, event_id, car_class))
    return self.changes()

  def run_list(self, event_id=None, entry_id=None, state=None, max_run_id=None, limit=None, offset=None, sort='A'):
    sql = "SELECT * FROM runs WHERE 1 "
    args = []
    if event_id is None and entry_id is None:
      raise Exception("Oops! missing event_id or entry_id")
    if event_id is not None:
      sql += " AND event_id=? "
      args.append(event_id)
    if entry_id in ('noassign', 'null'):
      sql += " AND entry_id ISNULL "
    elif entry_id not in (None, 'all'):
      sql += " AND entry_id=? "
      args.append(entry_id)
    if isinstance(state, types.StringTypes):
      sql += " AND state = ? "
      args.append(state)
    elif isinstance(state, (list,tuple)) and len(state) > 0:
      sql += " AND state in (" + ','.join('?'*len(state)) + ") "
      args.extend(state)
    if max_run_id is not None:
      sql += " AND run_id<=? "
      args.append(max_run_id)
    if sort in ('d','D'):
      sql += " ORDER BY run_id DESC "
    elif sort in ('a','A'):
      sql += " ORDER BY run_id ASC "
    if limit:
      sql += " LIMIT ? "
      args.append(limit)
      if offset:
        sql += " OFFSET ? "
        args.append(offset)
    return self.query_all(sql, args)

  def run_count(self, event_id=None, entry_id=None, state=None, max_run_id=None):
    sql = "SELECT count(*) FROM runs WHERE 1 "
    args = []
    if event_id is None and entry_id is None:
      raise Exception("Oops! missing event_id or entry_id")
    if event_id is not None:
      sql += " AND event_id=? "
      args.append(event_id)
    if entry_id in ('noassign', 'null'):
      sql += " AND entry_id ISNULL "
    elif entry_id not in (None, 'all'):
      sql += " AND entry_id=? "
      args.append(entry_id)
    if isinstance(state, types.StringTypes):
      sql += " AND state = ? "
      args.append(state)
    elif isinstance(state, (list,tuple)) and len(state) > 0:
      sql += " AND state in (" + ','.join('?'*len(state)) + ") "
      args.extend(state)
    if max_run_id is not None:
      sql += " AND run_id<=? "
      args += [max_run_id]
    return self.query_single(sql, args)

  def run_started(self, event_id, time_ms, entry_id):
    self.cursor().execute("INSERT INTO runs (event_id, start_time_ms, entry_id, state) VALUES (?,?,?,'started')", (event_id, time_ms, entry_id))
    return self.last_insert_rowid()

  def run_finished(self, event_id, time_ms):
    with self:
      row = self.query_one("SELECT run_id FROM runs WHERE event_id=? AND NOT start_time_ms ISNULL AND start_time_ms > 0 AND start_time_ms <= ? AND state='started' ORDER BY run_id ASC LIMIT 1", (event_id, time_ms))
      if row is None:
        return None
      self.execute("UPDATE runs SET finish_time_ms=?, state='finished' WHERE run_id = ?", (time_ms, row['run_id']))
      return row['run_id']

  def run_split_1(self, event_id, time_ms):
    with self:
      row = self.query_one("SELECT run_id FROM runs WHERE event_id=? AND NOT start_time_ms ISNULL AND start_time_ms > 0 AND start_time_ms <= ? AND state='started' AND split_1_time_ms ISNULL ORDER BY run_id ASC LIMIT 1", (event_id, time_ms))
      if row is None:
        return None
      self.execute("UPDATE runs SET split_1_time_ms=? WHERE run_id = ?", (time_ms, row['run_id']))

  def run_split_2(self, event_id, time_ms):
    with self:
      row = self.query_one("SELECT run_id FROM runs WHERE event_id=? AND NOT start_time_ms ISNULL AND start_time_ms > 0 AND start_time_ms <= ? AND state='started' AND NOT split_1_time_ms ISNULL AND split_2_time_ms ISNULL ORDER BY run_id ASC LIMIT 1", (event_id, time_ms))
      if row is None:
        return None
      self.execute("UPDATE runs SET split_2_time_ms=? WHERE run_id = ?", (time_ms, row['run_id']))


#######################################
#######################################



