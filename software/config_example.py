import scoring_rules
import datetime
import os

# serial port paths
SERIAL_PORT_USB_RFID_READER = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A400BZJA-if00-port0"
SERIAL_PORT_WIRELESS_RFID_READER = ""
SERIAL_PORT_TAG_HEUER_520 = "/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller-if00-port0"
SERIAL_PORT_BARCODE_SCANNER = "/dev/serial/by-id/usb-Hand_Held_Products_4600R_08056A1430-if00"

SCORING_RULES_CLASS = scoring_rules.BasicRules

DEFAULT_SEASON = "ORG_%04d"  % datetime.date.today().year
DEFAULT_ORGANIZATION = "Oregon Rally Group"

# database paths
SCORING_DB_PATH = os.path.expanduser("~/database/scoring_002.db")

# Flask/Jinja config
TEMPLATES_AUTO_RELOAD = True

# printer config
LABEL_PRINTER_NAME = "Zebra_TLP2844"

# sound paths, these can be anything that the sox play command can open
SOUND_RFID_SCAN_GOOD = ""
SOUND_RFID_SCAN_BAD = ""
SOUND_BARCODE_SCAN_GOOD = ""
SOUND_BARCODE_SCAN_BAD = ""
SOUND_START = ""
SOUND_FINISH = ""
SOUND_FALSE_START = ""
SOUND_FALSE_FINISH = ""

