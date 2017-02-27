import logging
from util import *
import inspect, sys
from collections import OrderedDict

# customizable rules for calculating event scoring

def get_rule_sets():
  return OrderedDict(inspect.getmembers(sys.modules[__name__],lambda x: inspect.isclass(x) and issubclass(x,BasicRules)))


###########################################################

class BasicRules(object):
  """ Basic RallyX rules with no drop runs """

  name = "Basic RallyX Rules"

  # default rule settings
  car_class_list = ['TO','SA','PA','MA','SF','PF','MF','SR','PR','MR'] # short identifiers in prefered sort order
  car_class_names = { # long display names
    'SA':'Stock All',
    'PA':'Prepared All',
    'MA':'Modified All',
    'SF':'Stock Front',
    'PF':'Prepared Front',
    'MF':'Modified Front',
    'SR':'Stock Rear',
    'PR':'Prepared Rear',
    'MR':'Modified Rear',
    'TO':'Time Only',
    }
  car_class_alias = {} # used for assigning alternate names for classes, useful for importing
  cone_penalty = 2
  gate_penalty = 10
  dnf_penalty = 0 # DNF bogey time
  min_runs = 1 # default, these will be updated when sync'ed with the event in the database
  max_runs = 5 # default, these will be updated when sync'ed with the event in the database
  drop_runs = 0 # a value of None disables drop runs for this rule set, where as 0 allows it to be used

  def __init__(self, **kwarg):
    self.log = kwarg.get('logger', logging.getLogger(__name__))


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

  def calc_dnf(self, db, run_id):
    # calculate a value for a DNF/DNS
    # some rule sets have a DNF counted as a bogey time
    return 0

  def recalc_run(self, db, run_id):
    with db:
      run = db.query_one("SELECT run_id, entry_id, start_time_ms, finish_time_ms, split_1_time_ms, split_2_time_ms, cones, gates FROM runs WHERE run_id=? AND NOT deleted", (run_id,))
      if run is None:
        return
      run['raw_time'] = None
      run['total_time'] = None
      run['raw_time_ms'] = None
      run['total_time_ms'] = None
      run['run_number'] = None
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
        run['raw_time'] = format_time(run['raw_time_ms'])
        run['total_time'] = format_time(run['total_time_ms'])
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
          run['run_number'] = row['run_count']

      db.execute("UPDATE runs SET recalc=0, raw_time=:raw_time, total_time=:total_time, raw_time_ms=:raw_time_ms, total_time_ms=:total_time_ms, run_number=:run_number WHERE run_id=:run_id", run)


  def recalc_entry(self, db, entry_id):
    self.log.debug("recalc_entry: %r", entry_id)
    if entry_id is None:
      return
    with db:
      entry = {'entry_id':entry_id}
      penalty_time_ms = db.query_single("SELECT SUM(time_ms) FROM penalties WHERE entry_id=? AND NOT deleted", (entry_id,))
      entry['event_penalties'] = format_time(penalty_time_ms, None)

      dropped_runs = []
      scored_runs = db.query_all("SELECT run_id, start_time_ms, finish_time_ms, total_time_ms FROM runs WHERE state = 'scored' AND entry_id=? AND NOT deleted", (entry_id,))

      self.log.debug("len(scored_runs) = %r", len(scored_runs))

      # sort runs
      scored_runs.sort(cmp=time_cmp, key=lambda r: r['total_time_ms'])

      # drop extra runs beyond max_runs
      dropped_runs += scored_runs[self.max_runs:]
      del scored_runs[self.max_runs:]
      
      self.log.debug("len(scored_runs) = %r", len(scored_runs))

      # regular drop runs
      if len(scored_runs) > self.min_runs and self.drop_runs > 0:
        dropped_runs += scored_runs[-self.drop_runs:]
        del scored_runs[-self.drop_runs:]
      
      self.log.debug("len(scored_runs) = %r", len(scored_runs))
      
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
        entry['event_time'] = format_time(entry['event_time_ms'],'PENDING')

      db.execute("UPDATE entries SET recalc=0, event_time_ms=:event_time_ms, event_time=:event_time, event_penalties=:event_penalties, event_runs=:event_runs WHERE entry_id=:entry_id", entry)


#  def recalc_run_count(self, db, entry_id):
#    with db:
#      run_count = 0
#      cur = db.cursor()
#      for runs in db.query_all("SELECT run_id, state FROM runs WHERE NOT deleted AND entry_id=?", (entry_id,)):
#        if run['state'] in ('scored','finished','started'):
#          run_count+=1
#          cur.execute("UPDATE runs SET run_count=? WHERE run_id=?", (run_count, run['run_id']))
#        else:
#          cur.execute("UPDATE runs SET run_count=NULL WHERE run_id=?", (run['run_id'],))

###########################################################
###########################################################

class ORG_RallyCross_Rules(BasicRules):
  """ Oregon Rally Group rules based on 2016 SCCA RallyX rules and regional supplimental rules """

  name = "ORG Rally Cross"
  drop_runs = 1
  min_runs = 3


###########################################################
###########################################################

class NWRA_RallyCross_Rules(BasicRules):
  name = "NWRA Rally Cross"
  car_class_list = ['SA','PA','MA','SF','PF','MF','SR','PR','MR']
  car_class_names = {
    'SA':'Stock All',
    'PA':'Prepared All',
    'MA':'Modified All',
    'SF':'Stock Front',
    'PF':'Prepared Front',
    'MF':'Modified Front',
    'SR':'Stock Rear',
    'PR':'Prepared Rear',
    'MR':'Modified Rear',
    'TO':'Time Only'
    }
  car_class_alias = {
    'Mod AWD':'MA',
    'Prepared AWD':'PA',
    'Stock AWD':'SA',
    'Mod FWD':'MF',
    'Prepared FWD':'PF',
    'Stock FWD':'SF',
    'Mod RWD':'MR',
    'Prepared RWD':'PR',
    'Stock RWD':'SR',
      }
  
  def calc_dnf(db, run_id):
    pass # FIXME


class NWRA_RallySprint_Rules(BasicRules):
  "NWRA Rally Sprint"
  car_class_list = ['4O','4U','2O','2U']
  car_class_names = {
    '4O':'AWD Over',
    '4U':'AWD Under',
    '2O':'2WD Over',
    '2U':'2WD Under',
    }
  car_class_alias = {
      'AWD Over':'AO',
      'AWD Under':'AU',
      '2WD Over':'2O',
      '2WD Under':'2U',
      }
  cone_penalty = 30
  gate_penalty = 50
  dnf_penalty = 120 # 2 minutes

  def calc_dnf(db, run_id):
    pass # FIXME


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
