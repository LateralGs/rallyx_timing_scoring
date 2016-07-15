import logging
from util import *

# customizable rules for calculating event scoring

###########################################################

class BasicRules(object):
  """ Basic RallyX rules with no drop runs """
  def __init__(self, **kwarg):
    self.log = kwarg.get('logger', logging.getLogger(__name__))
    self.cone_penalty = kwarg.get('cone_penalty', 2)
    self.gate_penalty = kwarg.get('gate_penalty', 10)
    self.min_runs = kwarg.get('min_runs', 3)
    self.max_runs = kwarg.get('max_runs', 5)
    self.drop_runs = kwarg.get('drop_runs', 0) # not used for BasicRules, placeholder for those that do
    self.car_class_list = ['TO','SA','PA','MA','SF','PF','MF','SR','PR','MR']
    self.car_class_names = {
      'SA':'Stock All',
      'PA':'Prepared All',
      'MA':'Modified All',
      'SF':'Stock Front',
      'PF':'Prepared Front',
      'MF':'Modified Front',
      'SR':'Stock Rear',
      'PR':'Prepared Rear',
      'MR':'Modified Rear',
      'TO':'Time Only'}


  def sync(self, db):
    if not db:
      return 
    # make sure we have the current settings from the database for this instance
    event = db.event_get(db.reg_get_int('active_event_id'))
    if event:
      self.max_runs = event['max_runs']
      self.drop_runs = event['drop_runs']


  def run_recalc(self, db, run_id):
    run = db.run_get(run_id)
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
    elif run['start_time_ms'] is None and run['finish_time_ms'] is None:
      pass
    elif run['finish_time_ms'] is None:
      pass
    elif run['start_time_ms'] is None:
      total_time_ms = raw_time_ms = run['finish_time_ms']
      if run['cones']:
        total_time_ms += run['cones'] * self.cone_penalty * 1000 # penalty is in seconds, we need milliseconds
      if run['gates']:
        total_time_ms += run['gates'] * self.gate_penalty * 1000 # penalty is in seconds, we need milliseconds
      raw_time = format_time(raw_time_ms)
      total_time = format_time(total_time_ms)
    elif run['finish_time_ms'] <= run['start_time_ms']:
      raw_time = "INVALID"
      total_time = "INVALID"
    else:
      total_time_ms = raw_time_ms = run['finish_time_ms'] - run['start_time_ms']
      if run['cones']:
        total_time_ms += run['cones'] * self.cone_penalty * 1000 # penalty is in seconds, we need milliseconds
      if run['gates']:
        total_time_ms += run['gates'] * self.gate_penalty * 1000 # penalty is in seconds, we need milliseconds
      raw_time = format_time(raw_time_ms)
      total_time = format_time(total_time_ms)

    if run['entry_id'] is not None:
      run_count = db.run_count(run['event_id'], run['entry_id'], state_filter=('scored','started','finished'), max_run_id=run_id)

    db.run_update(run_id, raw_time=raw_time, total_time=total_time, raw_time_ms=raw_time_ms, total_time_ms=total_time_ms, run_count=run_count)


  def entry_recalc(self, db, entry_id):
    # calculate event_time_ms, event_time
    entry_runs = db.run_list(entry_id=entry_id, state_filter=('scored',))
    self.log.debug(entry_runs)

    # limit scored runs to max_runs
    scored_runs = entry_runs[:self.max_runs]
    scored_run_count = len(scored_runs)
    self.log.debug("scored: %r", scored_runs)

    penalty_time_ms = db.query_singleton("SELECT SUM(time_ms) FROM penalties WHERE entry_id=?", entry_id)
    penalty_time = format_time(penalty_time_ms, None)

    event_time_ms = None
    event_time = None
    event_dnf = False
    for run in scored_runs:
      if run['start_time_ms'] == 0 or run['finish_time_ms'] == 0:
        event_dnf = True
        break;
      elif run['total_time_ms']:
        if event_time_ms is None:
          event_time_ms = run['total_time_ms']
        else:
          event_time_ms += run['total_time_ms']

    if event_dnf:
      event_time = "DNF"
      event_time_ms = 0
    elif penalty_time_ms is None:
      event_time = format_time(event_time_ms)
    else:
      event_time_ms += penalty_time_ms
      event_time = format_time(event_time_ms)

    db.entry_update(entry_id=entry_id, event_time_ms=event_time_ms, event_time=event_time, event_penalties=penalty_time, scored_runs=scored_run_count)

    self.run_count_recalc(db, entry_id)


  def run_count_recalc(self, db, entry_id):
    # update run counts
    entry_runs = db.run_list(entry_id=entry_id)
    run_count = 0
    for run in entry_runs:
      if run['state'] in ('scored','finished','started'):
        run_count+=1
        db.run_update(run_id=run['run_id'], run_count=run_count)
      else:
        db.run_update(run_id=run['run_id'], run_count=None)


  def event_recalc(self, db, event_id):
    entries = db.entry_id_list(event_id)
    for entry in entries:
      self.entry_recalc(db, entry['entry_id'])


  def event_finalize(self, db, event_id):
    """ Add DNS runs to anyone that has less than max_runs """
    entries = db.entry_id_list(event_id)
    for entry in entries:
      run_count = db.run_count(event_id, entry['entry_id'], state_filter=('scored','started','finished'))
      self.log.debug(run_count)
      for count in range(run_count+1, self.max_runs+2):
        db.run_insert(event_id=event_id, entry_id=entry['entry_id'], start_time_ms=0, raw_time='DNS', total_time='DNS', run_count=count, state='scored')
      self.entry_recalc(db, entry['entry_id'])


  def season_recalc(self, db):
    raise NotImplementedError()


###########################################################
###########################################################

class ORG_Rules(BasicRules):
  """ Oregon Rally Group rules based on 2016 SCCA RallyX rules and regional supplimental rules """
  def __init__(self, **kwarg):
    super(ORG_Rules,self).__init__(**kwarg)
    self.drop_events = kwarg.get('drop_events', 1)
    self.season_points_pos = [20, 18, 16, 14, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2]
    self.season_points_finish = 2
    self.season_points_dnf = 1


  def entry_recalc(self, db, entry_id):
    # calculate event_time_ms, event_time and drop runs
    entry_runs = self.run_list(entry_id=entry_id, state_filter=('scored',))
    self.log.debug(entry_runs)

    dropped_runs = []
    scored_runs = []

    # make sure we only drop if we are more than min runs
    max_drop = min(self.max_drop_runs, self.max_runs-self.min_runs)

    # drop runs that are beyond max_runs
    for i in range(len(entry_runs)):
      if i >= self.max_runs:
        dropped_runs.append(entry_runs[i])
      else:
        scored_runs.append(entry_runs[i])

    scored_run_count = len(scored_runs)

    self.log.debug("scored: %r", scored_runs)
    self.log.debug("dropped: %r", dropped_runs)

    # sort runs then find out which runs we drop
    scored_runs.sort(cmp=time_cmp, key=lambda r: r['total_time_ms'])
    dropped_runs += scored_runs[self.max_runs-self.max_drop:]
    del scored_runs[self.max_runs-max_drop:]

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
    
    # update dropped runs
    for run in entry_runs:
      if run in dropped_runs:
        self.run_update(run_id=run['run_id'], drop_run=1)
      else:
        self.run_update(run_id=run['run_id'], drop_run=0)
    
    # update run counts
    entry_runs = db.run_list(entry_id=entry_id)
    run_count = 0
    for run in entry_runs:
      if run['state'] in ('scored','finished','started'):
        run_count+=1
        db.run_update(run_id=run['run_id'], run_count=run_count)
      else:
        db.run_update(run_id=run['run_id'], run_count=None)


###########################################################
###########################################################

class NWRA_Rules(BasicRules):
  """ NorthWest Rally Asscociation rules based on 2016 SCCA RallyX rules and regional supplimental rules """

  def __init__(self, **kwarg):
    super(NWRA_Rules,self).__init__(**kwarg)


  def bogey_time(self, db, entry_id, run_count):
    car_class = db.query_singleton("SELECT car_class FROM entries WHERE entry_id=?", entry_id)
    time_ms = db.query_singleton("SELECT MAX(total_time_ms) FROM runs, entries WHERE runs.entry_id=entries.entry_id AND runs.run_count=? AND entries.car_class=?", run_count, car_class)
    if time_ms:
      return time_ms
    else:
      return 0
  

  def entry_recalc(self, db, entry_id):
    # calculate event_time_ms, event_time
    entry_runs = db.run_list(entry_id=entry_id, state_filter=('scored',))
    self.log.debug(entry_runs)

    # limit scored runs to max_runs
    scored_runs = entry_runs[:self.max_runs]
    scored_run_count = len(scored_runs)
    self.log.debug("scored: %r", scored_runs)

    penalty_time_ms = db.query_singleton("SELECT SUM(time_ms) FROM penalties WHERE entry_id=?", entry_id)
    penalty_time = format_time(penalty_time_ms, None)

    event_time_ms = None
    event_time = None
    for run in scored_runs:
      if run['start_time_ms'] == 0 or run['finish_time_ms'] == 0:
        if event_time_ms is None:
          event_time_ms = self.bogey_time(db, entry_id, run['run_count'])
        else:
          event_time_ms += self.bogey_time(db, entry_id, run['run_count'])
      elif run['total_time_ms']:
        if event_time_ms is None:
          event_time_ms = run['total_time_ms']
        else:
          event_time_ms += run['total_time_ms']

    if event_time_ms is not None:
      if penalty_time_ms is None:
        event_time = format_time(event_time_ms)
      else:
        event_time_ms += penalty_time_ms
        event_time = format_time(event_time_ms)

    db.entry_update(entry_id=entry_id, event_time_ms=event_time_ms, event_time=event_time, event_penalties=penalty_time, scored_runs=scored_run_count)

    self.run_count_recalc(db, entry_id)


###########################################################
###########################################################
