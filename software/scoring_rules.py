import logging
from util import *
import inspect, sys
from collections import OrderedDict

# customizable rules for calculating event scoring

def get_rule_sets():
  return OrderedDict(inspect.getmembers(sys.modules[__name__],lambda x: inspect.isclass(x) and issubclass(x,DefaultRules)))


###########################################################

class DefaultRules(object):
  """ Basic RallyX rules with no drop runs """

  name = "Default Rally Cross Rules"

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
  cone_penalty = 2 # seconds
  gate_penalty = 10 # seconds
  dnf_penalty = 0 # seconds, DNF bogey time
  min_runs = 1 # number of runs needed before drop runs can be used
  max_runs = 5 # total number of scored runs
  drop_runs = 0 # number of runs allowed to be dropped

  def __init__(self, **kwarg):
    self.log = kwarg.get('logger', logging.getLogger(__name__))


  def calc_dnf(self, db, run_id):
    # time penalty in milliseconds or None to have the DNF stand
    return self.dnf_penalty * 1000


  def recalc_run(self, db, run_id):
    self.log.debug("recalc_run: %r", run_id)
    with db:
      run = db.query_one("SELECT run_id, entry_id, start_time_ms, finish_time_ms, split_1_time_ms, split_2_time_ms, cones, gates, dns_dnf FROM runs WHERE run_id=? AND NOT deleted", (run_id,))
      if run is None:
        return
      run['raw_time'] = None
      run['total_time'] = None
      run['raw_time_ms'] = None
      run['total_time_ms'] = None
      run['run_number'] = None
      if run['dns_dnf'] == 1:
        run['raw_time'] = "DNS"
        run['total_time'] = "DNS"
      elif run['dns_dnf'] > 1:
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
      entry['event_penalties'] = format_time(penalty_time_ms)

      dropped_runs = []
      scored_runs = db.query_all("SELECT run_id, dns_dnf, start_time_ms, finish_time_ms, total_time_ms FROM runs WHERE state = 'scored' AND entry_id=? AND NOT deleted", (entry_id,))

      # sort runs based on time or dnf status
      scored_runs.sort(cmp=run_cmp)

      # remove extra runs beyond max_runs
      dropped_runs += scored_runs[self.max_runs:]
      del scored_runs[self.max_runs:]

      # removed drop runs beyond min runs
      if len(scored_runs) > self.min_runs and self.drop_runs > 0:
        dropped_runs += scored_runs[-self.drop_runs:]
        del scored_runs[-self.drop_runs:]
      
      entry['event_runs'] = len(scored_runs)
      entry['event_time_ms'] = penalty_time_ms if penalty_time_ms is not None else 0
      entry['event_time'] = None
      event_dnf = False
      for run in scored_runs:
        if run['dns_dnf'] > 0:
          dnf_time_ms = self.calc_dnf(db, run['run_id'])
          if dnf_time_ms is None:
            event_dnf = True
            break
          else:
            entry['event_time_ms'] += dnf_time_ms
        elif run['total_time_ms']:
          entry['event_time_ms'] += run['total_time_ms']

      if event_dnf:
        entry['event_time'] = "DNF"
        entry['event_time_ms'] = 0
      else:
        entry['event_time'] = format_time(entry['event_time_ms']) if entry['event_time_ms'] > 0 else None

      db.execute("UPDATE entries SET recalc=0, event_time_ms=:event_time_ms, event_time=:event_time, event_penalties=:event_penalties, event_runs=:event_runs WHERE entry_id=:entry_id", entry)


###########################################################
###########################################################

class ORG_RallyCross_Rules(DefaultRules):
  """ Oregon Rally Group rules based on 2016 SCCA RallyX rules and regional supplimental rules """

  name = "ORG Rally Cross"
  drop_runs = 1
  min_runs = 3

  def calc_dnf(self, db, run_id):
    return None # a DNF is a DNF, you already got a drop run


###########################################################
###########################################################

class NWRA_RallyCross_Rules(DefaultRules):
  name = "NWRA Rally Cross"
  car_class_list = ['SA','PA','MA','SF','PF','MF','SR','PR','MR','TO']
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
    'Time Only':'TO'
      }
  dnf_penalty = 10
  
  def calc_dnf(self, db, run_id):
    # dnf is bogey_time_ms + slowest time in class for run_number
    entry_run = db.query_one("SELECT entries.car_class, entries.event_id, runs.run_number FROM entries, runs WHERE entries.entry_id=runs.entry_id AND runs.run_id=? AND NOT entries.deleted AND NOT runs.deleted", (run_id,))
    if entry_run is None:
      return None
    slowest_time_ms =  db.query_single("SELECT MAX(raw_time_ms) FROM entries, runs WHERE entries.entry_id=runs.entry_id AND runs.state = 'scored' AND runs.event_id=? AND runs.run_number=? AND entries.car_class=? AND NOT entries.deleted AND NOT runs.deleted", (entry_run['event_id'], entry_run['run_number'], entry_run['car_class']))
    if slowest_time_ms is None:
      return None
    else:
      return slowest_time_ms + (self.dnf_penalty * 1000)


###########################################################
###########################################################


class NWRA_RallySprint_Rules(DefaultRules):
  name = "NWRA Rally Sprint"
  car_class_list = ['4O','4U','2O','2U']
  car_class_names = {
    '4O':'AWD Over',
    '4U':'AWD Under',
    '2O':'2WD Over',
    '2U':'2WD Under',
    }
  car_class_alias = {
      'AWD Over':'4O',
      'AWD Under':'4U',
      '2WD Over':'2O',
      '2WD Under':'2U',
      }
  cone_penalty = 30
  gate_penalty = 50
  dnf_penalty = 120 # 2 minutes

  def calc_dnf(self, db, run_id):
    # dnf is bogey_time_ms + slowest time in class for run_number
    entry_run = db.query_one("SELECT entries.car_class, entries.event_id, runs.run_number FROM entries, runs WHERE entries.entry_id=runs.entry_id AND runs.run_id=? AND NOT entries.deleted AND NOT runs.deleted", (run_id,))
    if entry_run is None:
      return None
    slowest_time_ms =  db.query_single("SELECT MAX(raw_time_ms) FROM entries, runs WHERE entries.entry_id=runs.entry_id AND runs.state = 'scored' AND runs.event_id=? AND runs.run_number=? AND entries.car_class=? AND NOT entries.deleted AND NOT runs.deleted", (entry_run['event_id'], entry_run['run_number'], entry_run['car_class']))
    if slowest_time_ms is None:
      return None
    else:
      return slowest_time_ms + (self.dnf_penalty * 1000)


###########################################################
###########################################################

