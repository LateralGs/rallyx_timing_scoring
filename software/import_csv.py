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

if len(sys.argv) < 3:
  logging.error("usage: python import_csv.py <csv file> <segment> <command>")
  sys.exit(1)

csv_path = sys.argv[1]
segment = sys.argv[2].lower()
command = sys.argv[3].lower()

# commands are:
#   update - update existing drivers and entries, insert new ones
#   insert_only - insert new drivers and entries only

if command not in ('update', 'insert_only'):
  logging.error("Invalid command, %r", command)
  logging.info("Commands accepted: ['update', 'insert_only']")
  sys.exit(1)

logging.info("Segment = %r", segment)

with ScoringDatabase(config.SCORING_DB_PATH) as db:
  active_event_id = db.reg_get_int("active_event_id")
  if active_event_id is None:
    logging.error("No active event set!")
    sys.exit(1)
  
  with open(csv_path) as csv_file:
    reader = csv.DictReader(csv_file)
    logging.info(reader.fieldnames)
    for row in reader:
      if row['Segment Name'].lower() == segment:
        logging.debug(row)
        # check if driver exists based on msreg unique id
        driver = db.driver_by_msreg(row['Unique ID'])
        if driver is None:
          # TODO add ability to detect drivers without msreg number set based on name
          driver_id = db.driver_insert(first_name=row['First Name'], last_name=row['Last Name'], msreg_number=row['Unique ID'], scca_number=row['Member #'], addr_city=row['City'], addr_state=row['State'], addr_zip=row['Zip Code'])
          driver = db.driver_get(driver_id)
          logging.info("Created driver, %r", driver)
        elif command == 'update':
          db.driver_update(driver_id=driver['driver_id'], first_name=row['First Name'], last_name=row['Last Name'], scca_number=row['Member #'], addr_city=row['City'], addr_state=row['State'], addr_zip=row['Zip Code'])
          driver = db.driver_get(driver['driver_id'])
          logging.info("Updated driver, %r", driver)

        if row['Class'] not in config.CAR_CLASSES:
          logging.error("Invalid car class, %r", row['Class'])

        entry = db.entry_by_driver(active_event_id, driver['driver_id'])
        if entry is None:
          entry_note = "1st Event!" if row['1st Event?'] == 'Yes' else None
          entry_id = db.entry_insert(event_id=active_event_id, driver_id=driver['driver_id'], car_year=row['Year'], car_make=row['Make'], car_model=row['Model'], car_color=row['Color'], entry_note=entry_note, car_class=row['Class'])
          entry = db.entry_get(entry_id)
          logging.info("Created entry, %r", entry)
        elif command == 'update':
          # make sure we dont clobber notes
          if entry['entry_note'] is None:
            entry_note = "1st Event!" if row['1st Event?'] == 'Yes' else None
          else:
            entry_note = entry['entry_note']
          db.entry_update(entry_id=entry['entry_id'], car_year=row['Year'], car_make=row['Make'], car_model=row['Model'], car_color=row['Color'], entry_note=entry_note, car_class=row['Class'])
          entry = db.entry_get(entry['entry_id'])
          logging.info("Updated entry, %r", entry)


