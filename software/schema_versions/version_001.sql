
CREATE TABLE IF NOT EXISTS registry (
  key   TEXT PRIMARY KEY NOT NULL,
  value TEXT
);

CREATE TABLE IF NOT EXISTS drivers (
  driver_id       INTEGER PRIMARY KEY,
  first_name      TEXT,
  last_name       TEXT,
  alt_name        TEXT,
  msreg_number    TEXT,
  scca_number     TEXT,
  license_number  TEXT,
  addr_line_1     TEXT,
  addr_line_2     TEXT,
  addr_city       TEXT,
  addr_state      TEXT,
  addr_zip        TEXT,
  phone           TEXT,
  email           TEXT,
  license_data    TEXT, -- decoded data from barcode on drivers license
  driver_note     TEXT
);

CREATE TABLE IF NOT EXISTS entries (
  entry_id        INTEGER PRIMARY KEY,
  event_id        INT NOT NULL,
  driver_id       INT NOT NULL,
  rfid_number     TEXT,
  dual_driver     INT NOT NULL DEFAULT 0,
  car_year        TEXT,
  car_make        TEXT,
  car_model       TEXT,
  car_color       TEXT,
  car_number      TEXT NOT NULL DEFAULT '0',
  car_class       TEXT NOT NULL DEFAULT 'TO',
  season_points   INT NOT NULL DEFAULT 1,
  work_assign     TEXT,
  entry_note      TEXT,
  event_time_ms   INT,
  event_time      TEXT,
  scored_runs     INT NOT NULL DEFAULT 0,
  show_scores     INT NOT NULL DEFAULT 1 -- should the scores be publicly visible
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
  run_note        TEXT
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
  national      INT DEFAULT 0,
  season_points INT DEFAULT 1,
  visible       INT DEFAULT 1, -- Is this event visible in the scoring browser
  event_note    TEXT
);

