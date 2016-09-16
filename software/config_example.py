import scoring_rules
import datetime
import os

SCORING_RULES_CLASS = scoring_rules.BasicRules

DEFAULT_SEASON = "ORG_%04d"  % datetime.date.today().year
DEFAULT_ORGANIZATION = "Oregon Rally Group"

# database paths
SCORING_DB_PATH = os.path.expanduser("~/database/scoring_002.db")

# Flask/Jinja config
TEMPLATES_AUTO_RELOAD = True

# printer config
LABEL_PRINTER_NAME = "Zebra_TLP2844"

SOUNDS = {}
SOUNDS['rfid_good'] = ""
SOUNDS['rfid_bad'] = ""
SOUNDS['barcode_good'] = ""
SOUNDS['barcode_bad'] = ""
SOUNDS['start_good'] = ""
SOUNDS['start_bad'] = ""
SOUNDS['finish_good'] = ""
SOUNDS['finish_bad'] = ""
SOUNDS['split_1'] = ""
SOUNDS['split_2'] = ""

