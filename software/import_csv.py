#!/usr/bin/python2
import logging
try:
  import tendo.colorer
except ImportError:
  print "no colorer"
logging.basicConfig(level=logging.DEBUG) # initialize this early so we get all output

import sys, csv

import config
from sql_db import ScoringDatabase

# handle mapping class names from msreg to our class identifiers
class_mapping = {
    'Stock AWD': 'SA',
    'Prepared AWD':'PA',
    'Mod AWD': 'MA',
    'Stock FWD': 'SF',
    'Prepared FWD':'PF',
    'Mod FWD': 'MF',
    'Stock RWD': 'SR',
    'Prepared RWD':'PR',
    'Mod RWD': 'MR',
    }

if len(sys.argv) < 1:
  logging.error("usage: python import_csv.py <csv file>")
  sys.exit(1)

csv_path = sys.argv[1]
segment_filter = sys.argv[2] if len(sys.argv) > 2 else None
class_filter = sys.argv[3:]

with ScoringDatabase(config.SCORING_DB_PATH) as db:
  active_event_id = db.reg_get_int("active_event_id")
  if active_event_id is None:
    logging.error("No active event set!")
    sys.exit(1)

  rules = config.SCORING_RULES_CLASS()
  rules.sync(db)
  
  with open(csv_path) as csv_file:
    reader = csv.DictReader(csv_file)
    logging.info(reader.fieldnames)
    for row in reader:
      logging.debug(row)

      if segment_filter and row['Segment Name'] != segment_filter:
        continue

      if len(class_filter) > 0 and row['Class'] not in class_filter:
        continue
      
      if 'Status' in row and row['Status'] == 'Cancelled':
        continue # skip people that have canceled but are still listed

      if 'card_number' not in row:
        row['card_number'] = None

      # check if driver exists based on msreg unique id
      driver = db.driver_by_msreg(row['Unique ID'])
      if driver is None:
        # TODO add ability to detect drivers without msreg number set based on name
        driver_id = db.driver_insert(first_name=row['First Name'], last_name=row['Last Name'], msreg_number=row['Unique ID'], scca_number=row['Member #'], addr_city=row['City'], addr_state=row['State'], addr_zip=row['Zip Code'], card_number=row['card_number'])
        logging.info("Created driver, %r", driver_id)
      else:
        driver_id = driver['driver_id']
        db.driver_update(driver_id=driver_id, first_name=row['First Name'], last_name=row['Last Name'], scca_number=row['Member #'], addr_city=row['City'], addr_state=row['State'], addr_zip=row['Zip Code'], card_number=row['card_number'])
        logging.info("Updated driver, %r", driver['driver_id'])

      car_class = row['Class']

      if car_class in class_mapping:
        car_class = class_mapping[car_class]

      if car_class not in rules.car_class_list:
        logging.error("Invalid car class, %r", row['Class'])
        continue

      entry = db.entry_by_driver(active_event_id, driver_id)
      if entry is None:
        entry_note = None # add note here if we want one
        entry_id = db.entry_insert(event_id=active_event_id, driver_id=driver_id, car_number=row['No.'], car_year=row['Year'], car_make=row['Make'], car_model=row['Model'], car_color=row['Color'], entry_note=entry_note, car_class=car_class)
        entry = db.entry_get(entry_id)
        logging.info("Created entry, %r", entry_id)
      else:
        # make sure we dont clobber notes
        if entry['entry_note'] is None:
          entry_note = None # add note here if we want one
        else:
          entry_note = entry['entry_note']
        db.entry_update(entry_id=entry['entry_id'], car_number=row['No.'], car_year=row['Year'], car_make=row['Make'], car_model=row['Model'], car_color=row['Color'], entry_note=entry_note, car_class=car_class)
        logging.info("Updated entry, %r", entry['entry_id'])


