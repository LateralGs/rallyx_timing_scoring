


# customizable rules for calculating event scoring

###########################################################

class BasicRules(ScoringRules):
  """ Basic RallyX rules with no drop runs """
  def __init__(self, max_runs):
    self.cone_penalty = 2
    self.gate_penalty = 10
    self.max_runs = 5
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

    db.entry_update(entry_id=entry_id, event_time_ms=event_time_ms, event_time=event_time, scored_runs=scored_run_count)


  def event_recalc(self, db, event_id):
    entries = db.entry_id_list(event_id)
    for entry in entries:
      self.entry_recalc(entry['entry_id'])


  def event_finalize(self, db, event_id):
    """ Add DNS runs to anyone that has less than max_runs """
    entries = db.entry_id_list(event_id)
    for entry in entries:
      run_count = db.run_count(event_id, entry['entry_id'], state_filter=('scored','started','finished'))
      for count in range(run_count+1, self.max_runs+1):
        self.run_insert(event_id=event_id, start_time_ms=0, raw_time=DNS, total_time=DNS, run_count=count)
      self.entry_recalc(entry['entry_id'])


  def season_recalc(self, db):
    raise NotImplementedError()


###########################################################
###########################################################

class ORG_Rules(BasicRules):
  """ Oregon Rally Group rules based on 2016 SCCA RallyX rules and regional supplimental rules """
  def __init__(self, *arg, **kwarg):
    super(ORG_Rules,self).__init__(*arg, **kwarg)
    self.max_drop_runs = 1
    self.max_drop_events = 1
    self.min_runs = 3 # only drop runs if we are above min_runs
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
    
    for run in entry_runs:
      if run in dropped_runs:
        self.run_update(run_id=run['run_id'], drop_run=1)
      else:
        self.run_update(run_id=run['run_id'], drop_run=0)


###########################################################
###########################################################

def NWRA_Rules(BasicRules):
  """ NorthWest Rally Asscociation rules based on 2016 SCCA RallyX rules and regional supplimental rules """
  pass


###########################################################
###########################################################
