-- Registry tables are generic key/value stores

-- global registry table should never change
CREATE TABLE registry (
  key   TEXT PRIMARY KEY NOT NULL,
  value TEXT
);

-- per event registry entries
CREATE TABLE event_registry (
  event_id INTEGER NOT NULL,
  key   TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY ( event_id, key )
);

-- per driver registry entries
CREATE TABLE driver_registry (
  driver_id INTEGER NOT NULL,
  key   TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY ( driver_id, key )
);

-- per entry registry entries
CREATE TABLE entry_registry (
  entry_id INTEGER NOT NULL,
  key   TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY ( entry_id, key )
);


CREATE TABLE drivers (
  driver_id       INTEGER PRIMARY KEY, -- rowid
  first_name      TEXT,
  last_name       TEXT,
  msreg_number    TEXT,
  scca_number     TEXT,
  license_number  TEXT, -- competition or drivers license

  driver_note     TEXT,

  tracking_number TEXT, -- unique driver tracking number (rfid, barcode, etc.)

  deleted         INT NOT NULL DEFAULT 0, -- used instead of deleting from database
  timestamp       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- used for sorting and merging
);

CREATE TABLE entries (
  entry_id        INTEGER PRIMARY KEY, -- rowid
  event_id        INTEGER NOT NULL,
  driver_id       INTEGER NOT NULL,
  co_driver       TEXT, -- plain text field, not pointer to driver entry
  car_year        TEXT,
  car_make        TEXT,
  car_model       TEXT,
  car_color       TEXT,
  car_number      TEXT NOT NULL DEFAULT '0',
  car_class       TEXT NOT NULL DEFAULT 'TO',
  season_points   INT  NOT NULL DEFAULT 1, -- will this entry earn season points
  work_assignment TEXT,
  entry_note      TEXT,

  event_time_ms   INT,  -- total score for this entry
  event_time      TEXT,
  event_penalties TEXT, -- total penalties for event (not cones/gates)
  event_runs      INT NOT NULL DEFAULT 0, -- total scored runs for this event
  event_dnf       INT NOT NULL DEFAULT 0,

  scores_visible  INT NOT NULL DEFAULT 1, -- should the scores be publicly visible
  checked_in      INT NOT NULL DEFAULT 0,
  run_group       TEXT, -- which session did they race in (eg. AM, PM, ...)

  recalc          INT NOT NULL DEFAULT 0, -- request this entries total to be recalculated
  deleted         INT NOT NULL DEFAULT 0, -- used instead of deleting from database
  timestamp       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- used for sorting and merging
);

-- view adding driver name/card# to entries data, also filters deleted
CREATE VIEW driver_entries AS SELECT 
  entries.*,
  drivers.first_name,
  drivers.last_name,
  drivers.tracking_number
  FROM drivers, entries 
  WHERE drivers.driver_id == entries.driver_id AND NOT drivers.deleted AND NOT entries.deleted
  ORDER BY drivers.last_name, drivers.first_name;

CREATE TABLE runs (
  run_id          INTEGER PRIMARY KEY, -- rowid
  event_id        INTEGER NOT NULL,
  entry_id        INTEGER,

  -- input values
  cones           INT,
  gates           INT,
  dns_dnf         INT,  -- 1 = DNS, 2 = DNF
  start_time_ms   INT,
  finish_time_ms  INT,
  state           TEXT, -- started, finished, scored, tossout
  run_note        TEXT,
  split_1_time_ms INT,  -- split times
  split_2_time_ms INT,

  -- calculated values
  raw_time_ms     INT,  -- finish_time_ms - start_time_ms
  total_time_ms   INT,  -- raw_time_ms + penalty time
  raw_time        TEXT, -- string form of raw_time_ms
  total_time      TEXT, -- string form of total_time_ms or DNS/DNF
  drop_run        INT NOT NULL DEFAULT 0, -- used for regions that have drop runs
  run_number      INT,  -- runs start at 1
  sector_1_time   TEXT, -- split_1 - start
  sector_2_time   TEXT, -- split_2 - split_1
  sector_3_time   TEXT, -- finish - split_2

  recalc          INT NOT NULL DEFAULT 0, -- request this run to be recalculated
  deleted         INT NOT NULL DEFAULT 0, -- used instead of deleting from database
  timestamp       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- used for sorting and merging
);

CREATE TABLE times ( -- times triggered from external timing equipment
  time_id       INTEGER PRIMARY KEY, -- rowid
  event_id      INTEGER,
  channel       TEXT,
  time_ms       INT,
  invalid       INT NOT NULL DEFAULT 0,
  
  deleted       INT NOT NULL DEFAULT 0, -- used instead of deleting from database
  timestamp     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- used for sorting and merging
);

CREATE TABLE events (
  event_id      INTEGER PRIMARY KEY, -- rowid
  name          TEXT,
  location      TEXT,
  organization  TEXT,
  event_date    TEXT, -- RFC3339 format date YYYY-MM-DD
  season_name   TEXT,

  event_note    TEXT,
  max_runs      INT,
  drop_runs     INT, -- just in case we need to calc it per event
  rule_set      TEXT,

  deleted       INT   NOT NULL DEFAULT 0, -- used instead of deleting from database
  timestamp     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- used for sorting and merging
);

-- per event penalties (not cones/gates)
CREATE TABLE penalties (
  penalty_id    INTEGER PRIMARY KEY, -- rowid
  event_id      INTEGER NOT NULL,
  entry_id      INTEGER NOT NULL,
  time_ms       INT   DEFAULT 0,
  penalty_note  TEXT,

  deleted       INT   NOT NULL DEFAULT 0, -- used instead of deleting from database
  timestamp     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- used for sorting and merging
);

