import scoring_rules
import datetime

SCORING_RULES_CLASS = scoring_rules.BasicRules

DEFAULT_SEASON = "%04d"  % datetime.date.today().year
DEFAULT_ORGANIZATION = "Rally Group"

# database paths
SCORING_DB_PATH = "/home/user/database/scoring_003.db"

