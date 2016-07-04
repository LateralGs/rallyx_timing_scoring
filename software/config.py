#######################################
# All variables in this file should be derived from builtin types
# All variable names should be in all uppercase
# All variables sould be treated as constants
#######################################

# global constants
CAR_CLASSES = ['TO','SA','PA','MA','SF','PF','MF','SR','PR','MR']
CAR_CLASS_NAMES = {
    'SA':'Stock All',
    'PA':'Prepared All',
    'MA':'Modified All',
    'SF':'Stock Front',
    'PF':'Prepared Front',
    'MF':'Modified Front',
    'SR':'Stock Rear',
    'PR':'Prepared Rear',
    'MR':'Modified Rear',
    'TO':'Time Only'}

# rules
DROP_RUNS = 2
MIN_RUNS = 3
CONE_PENALTY = 2
GATE_PENALTY = 10
DROP_EVENTS=3
MIN_EVENTS=7

# default settings
DEFAULT_MAX_RUNS = 5
DEFAULT_DEADTIME_MS = 5000
DEFAULT_DEBOUNCE_MS = 20
DEFAULT_MAX_TIME_EVENTS = 20

DEFAULT_SEASON = "2016"
DEFAULT_ORGANIZATION = "ORG"

# serial port paths
SERIAL_PORT_RFID_READER = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A400C02I-if00-port0"
SERIAL_PORT_RALLYX_TIMER = "/dev/serial/by-id/usb-Teensyduino_USB_Serial_309640-if00"
SERIAL_PORT_TAG_HEUER_520 = "/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0"
SERIAL_PORT_LICENSE_SCANNER = "/dev/serial/by-id/usb-Hand_Held_Products_4600R_08056A1430-if00"

# season points values
SEASON_POINTS_POS = [20, 18, 16, 14, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2]
SEASON_POINTS_FINISH = 2
SEASON_POINTS_DNF = 1

# database paths
SCORING_DB_PATH = "db/scoring.db"

# Flask/Jinja config
TEMPLATES_AUTO_RELOAD = True

# printer config
PRINTER_NAME = "Zebra_TLP2844"
