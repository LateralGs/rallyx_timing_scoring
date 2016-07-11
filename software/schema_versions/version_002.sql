
-- registry table should never change
CREATE TABLE IF NOT EXISTS registry (
  key   TEXT PRIMARY KEY NOT NULL,
  value TEXT
);

CREATE TABLE IF NOT EXISTS drivers (
  driver_id       INTEGER PRIMARY KEY,
  first_name      TEXT,
  last_name       TEXT,
  alt_name        TEXT, -- use this instead of first_name (nickname)
  msreg_number    TEXT,
  scca_number     TEXT,
  license_number  TEXT, -- drivers license number
  addr_line_1     TEXT,
  addr_line_2     TEXT,
  addr_city       TEXT,
  addr_state      TEXT,
  addr_zip        TEXT,
  phone           TEXT,
  email           TEXT,
  driver_note     TEXT,

  card_number     TEXT -- unique driver card number (rfid, barcode, etc.)
);

CREATE TABLE IF NOT EXISTS entries (
  entry_id        INTEGER PRIMARY KEY,
  event_id        INT NOT NULL,
  driver_id       INT NOT NULL,
  dual_driver     INT NOT NULL DEFAULT 0,
  car_year        TEXT,
  car_make        TEXT,
  car_model       TEXT,
  car_color       TEXT,
  car_number      TEXT NOT NULL DEFAULT '0',
  car_class       TEXT NOT NULL DEFAULT 'TO',
  season_points   INT NOT NULL DEFAULT 1, -- will this entry earn season points
  work_assign     TEXT,
  entry_note      TEXT,
  event_time_ms   INT,  -- total score for this entry
  event_time      TEXT,
  event_points    INT, -- season points for this event
  scored_runs     INT NOT NULL DEFAULT 0,
  visible         INT NOT NULL DEFAULT 1, -- should the scores be publicly visible
  checked_in      INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
  run_id          INTEGER PRIMARY KEY,
  event_id        INT NOT NULL,
  entry_id        INT,
  cones           INT,
  gates           INT,
  start_time_ms   INT,  -- 0 == DNS
  finish_time_ms  INT,  -- 0 == DNF
  state           TEXT, -- started, finished, scored, tossout
  raw_time_ms     INT,
  total_time_ms   INT,
  raw_time        TEXT,
  total_time      TEXT,
  drop_run        INT NOT NULL DEFAULT 0,
  run_count       INT,
  run_note        TEXT,
  
  split_1_time_ms INT, -- split times
  split_2_time_ms INT,
  split_1_time    TEXT,
  split_2_time    TEXT,
);

CREATE TABLE IF NOT EXISTS times (
  time_id       INTEGER PRIMARY KEY,
  event_id      INT,
  channel       TEXT,
  time_ms       INT,
  invalid       INT NOT NULL DEFAULT 0,
  time_note     TEXT
);

CREATE TABLE IF NOT EXISTS events (
  event_id      INTEGER PRIMARY KEY,
  name          TEXT,
  location      TEXT,
  organization  TEXT,
  date          TEXT, -- RFC3339 format date YYYY-MM-DD
  season        TEXT,
  rule_set      TEXT, -- selects which ScoringRules instance to use
  season_points INT DEFAULT 1,
  visible       INT DEFAULT 1, -- Is this event publicly visible
  event_note    TEXT,
  max_runs      INT DEFAULT 3,
  drop_runs     INT DEFAULT 0,
);

-- entry per event penalties (not cones/gates)
CREATE TABLE IF NOT EXISTS penalties (
  penalty_id    INTEGER PRIMARY KEY,
  entry_id      INT NOT NULL,
  time_ms       INT DEFAULT 0,
  penalty_note  TEXT
  );
  
