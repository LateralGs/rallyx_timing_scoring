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
    active_event_id = db.reg_get('active_event_id')
    if not active_event_id:
      return
    event = db.query_one("SELECT max_runs, drop_runs FROM events WHERE event_id=?", (active_event_id,))
    if event:
      self.max_runs = event['max_runs']
      self.drop_runs = event['drop_runs']


  def run_recalc(self, db, run_id):
    with db:
      run = db.query_one("SELECT run_id, entry_id, start_time_ms, finish_time_ms, split_1_time_ms, split_2_time_ms, cones, gates FROM runs WHERE run_id=? AND NOT deleted", (run_id,))
      if run is None:
        return
      run['raw_time'] = None
      run['total_time'] = None
      run['raw_time_ms'] = None
      run['total_time_ms'] = None
      run['run_count'] = None
      if run['start_time_ms'] == 0:
        run['raw_time'] = "DNS"
        run['total_time'] = "DNS"
      elif run['finish_time_ms'] == 0:
        run['raw_time'] = "DNF"
        run['total_time'] = "DNF"
      elif run['start_time_ms'] is None and run['finish_time_ms'] is None:
        pass
      elif run['finish_time_ms'] is None:
        pass
      elif run['start_time_ms'] is None:
        run['total_time_ms'] = run['raw_time_ms'] = run['finish_time_ms']
        if run['cones']:
          run['total_time_ms'] += run['cones'] * self.cone_penalty * 1000 # penalty is in seconds, we need milliseconds
        if run['gates']:
          run['total_time_ms'] += run['gates'] * self.gate_penalty * 1000 # penalty is in seconds, we need milliseconds
        run['raw_time'] = format_time(raw_time_ms)
        run['total_time'] = format_time(total_time_ms)
      elif run['finish_time_ms'] <= run['start_time_ms']:
        run['raw_time'] = "INVALID"
        run['total_time'] = "INVALID"
      else:
        run['total_time_ms'] = run['raw_time_ms'] = run['finish_time_ms'] - run['start_time_ms']
        if run['cones']:
          run['total_time_ms'] += run['cones'] * self.cone_penalty * 1000 # penalty is in seconds, we need milliseconds
        if run['gates']:
          run['total_time_ms'] += run['gates'] * self.gate_penalty * 1000 # penalty is in seconds, we need milliseconds
        run['raw_time'] = format_time(run['raw_time_ms'])
        run['total_time'] = format_time(run['total_time_ms'])

      if run['entry_id'] is not None:
        row = db.query_one("SELECT count(*) as run_count FROM runs WHERE entry_id=:entry_id AND state != 'tossout' AND run_id <= :run_id AND NOT deleted", run)
        if row:
          run['run_count'] = row['run_count']

      db.execute("UPDATE runs SET recalc=0, raw_time=:raw_time, total_time=:total_time, raw_time_ms=:raw_time_ms, total_time_ms=:total_time_ms, run_count=:run_count WHERE run_id=:run_id", run)


  def entry_recalc(self, db, entry_id):
    with db:
      entry = {'entry_id':entry_id}
      penalty_time_ms = db.query_single("SELECT SUM(time_ms) FROM penalties WHERE entry_id=? AND NOT deleted", (entry_id,))
      entry['event_penalties'] = format_time(penalty_time_ms, None)

      dropped_runs = []
      scored_runs = db.query_all("SELECT run_id, start_time_ms, finish_time_ms, total_time_ms FROM runs WHERE state == 'scored' AND entry_id=? AND NOT deleted", (entry_id,))

      # sort runs
      scored_runs.sort(cmp=time_cmp, key=lambda r: r['total_time_ms'])

      # drop extra runs beyond max_runs
      dropped_runs += scored_runs[self.max_runs:]
      del scored_runs[self.max_runs:]

      # regular drop runs
      if len(scored_runs) > self.min_runs:
        dropped_runs += scored_runs[-self.drop_runs:]
        del scored_runs[-self.drop_runs:]
      
      entry['event_runs'] = len(scored_runs)
      entry['event_time_ms'] = penalty_time_ms if penalty_time_ms is not None else 0
      entry['event_time'] = None
      event_dnf = False
      for run in scored_runs:
        if run['start_time_ms'] == 0 or run['finish_time_ms'] == 0:
          event_dnf = True
          break
        elif run['total_time_ms']:
          if entry['event_time_ms'] is None:
            entry['event_time_ms'] = run['total_time_ms']
          else:
            entry['event_time_ms'] += run['total_time_ms']

      if event_dnf:
        entry['event_time'] = "DNF"
        entry['event_time_ms'] = 0
      else:
        entry['event_time'] = format_time(entry['event_time_ms'])

      db.execute("UPDATE entries SET recalc=0, event_time_ms=:event_time_ms, event_time=:event_time, event_penalties=:event_penalties, event_runs=:event_runs WHERE entry_id=:entry_id", entry)

  
  def run_count_recalc(self, db, entry_id):
    with db:
      run_count = 0
      cur = db.cursor()
      for runs in db.query_all("SELECT run_id, state FROM runs WHERE NOT deleted AND entry_id=?", (entry_id,)):
        if run['state'] in ('scored','finished','started'):
          run_count+=1
          cur.execute("UPDATE runs SET run_count=? WHERE run_id=?", (run_count, run['run_id']))
        else:
          cur.execute("UPDATE runs SET run_count=NULL WHERE run_id=?", (run['run_id'],))


#  def event_recalc(self, db, event_id):
#    for entry in db.cursor().execute("SELECT entry_id FROM entries WHERE event_id=? AND NOT deleted", (event_id,)):
#      self.entry_recalc(db, entry['entry_id'])


#  def event_finalize(self, db, event_id):
#    """ Add DNS runs to anyone that has less than max_runs """
#    with db:
#      cur = db.cursor()
#      for run in list(cur.execute("SELECT entry_id, COUNT(*) as run_count FROM runs WHERE state in ('started','finished','scored' AND event_id=? AND entry_id NOT NULL AND NOT deleted GROUP BY entry_id", (event_id,))):
#        for count in range(run['run_count']+1, self.max_runs+1):
#          db.cursor().execute("INSERT INTO runs (event_id, entry_id, start_time_ms, raw_time, total_time, run_count, state) VALUES (?, ?, 0, 'DNS', 'DNS', ?, 'scored')", (event_id, run['entry_id'], count))
#

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


###########################################################
###########################################################

#class NWRA_Rules(BasicRules):
#  """ NorthWest Rally Asscociation rules based on 2016 SCCA RallyX rules and regional supplimental rules """
#
#  def __init__(self, **kwarg):
#    super(NWRA_Rules,self).__init__(**kwarg)
#
#
#  def bogey_time(self, db, entry_id, run_count):
#    car_class = db.query_singleton("SELECT car_class FROM entries WHERE entry_id=?", entry_id)
#    time_ms = db.query_singleton("SELECT MAX(total_time_ms) FROM runs, entries WHERE runs.entry_id=entries.entry_id AND runs.run_count=? AND entries.car_class=?", run_count, car_class)
#    if time_ms:
#      return time_ms
#    else:
#      return 0
#  
#
#  def entry_recalc(self, db, entry_id):
#    # calculate event_time_ms, event_time
#    entry_runs = db.run_list(entry_id=entry_id, state_filter=('scored',))
#    self.log.debug(entry_runs)
#
#    # limit scored runs to max_runs
#    scored_runs = entry_runs[:self.max_runs]
#    scored_run_count = len(scored_runs)
#    self.log.debug("scored: %r", scored_runs)
#
#    penalty_time_ms = db.query_singleton("SELECT SUM(time_ms) FROM penalties WHERE entry_id=?", entry_id)
#    penalty_time = format_time(penalty_time_ms, None)
#
#    event_time_ms = None
#    event_time = None
#    for run in scored_runs:
#      if run['start_time_ms'] == 0 or run['finish_time_ms'] == 0:
#        if event_time_ms is None:
#          event_time_ms = self.bogey_time(db, entry_id, run['run_count'])
#        else:
#          event_time_ms += self.bogey_time(db, entry_id, run['run_count'])
#      elif run['total_time_ms']:
#        if event_time_ms is None:
#          event_time_ms = run['total_time_ms']
#        else:
#          event_time_ms += run['total_time_ms']
#
#    if event_time_ms is not None:
#      if penalty_time_ms is None:
#        event_time = format_time(event_time_ms)
#      else:
#        event_time_ms += penalty_time_ms
#        event_time = format_time(event_time_ms)
#
#    db.entry_update(entry_id=entry_id, event_time_ms=event_time_ms, event_time=event_time, event_penalties=penalty_time, scored_runs=scored_run_count)
#
#    self.run_count_recalc(db, entry_id)


###########################################################
###########################################################
