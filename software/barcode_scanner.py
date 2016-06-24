from serial_handler import SerialHandler, serial_wrapper
import re
from cStringIO import StringIO

BAUDRATE = 9600

CODE_ID_PDF417 = 'r'
CODE_ID_DATAMATRIX = 'w'
CODE_ID_QRCODE = 's'

class ReadTimeout(Exception):
  pass

def read_timeout_ex(s,n=1):
  s = s.read(n)
  if s == '':
    raise ReadTimeout()
  else:
    return s

def decode_license(data):
  try:
    sio = StringIO(data)
    if sio.read() != '@':
      return None
    header_groups = re.match("^\n\x1e\r([ a-zA-Z]{5})([0-9]{6})([0-9]{2})([0-9]{2})$",sio.read(18))
    if not header_groups:
      return None
    subfile_count = int(header_groups.group(4))
    subfile = {}
    for i in range(subfile_count):
      subfile_type = sio.read(2)
      subfile_offset = int(sio.read(4))
      subfile_length = int(sio.read(4))
      subfile[subfile_type] = (subfile_offset,subfile_length)
    elements = {}
    for i in range(subfile_count):
      subfile_data = ''
      c = sio.read(1)
      while c != '\r' and c != '':
        subfile_data += c
        c = sio.read(1)
      for element in subfile_data[2:].split('\n'):
        element = element.strip()
        if len(element) > 3:
          elements[element[0:3]] = element[3:]
    return elements
  except:
    return None

class BarcodeScanner(SerialHandler):
  def __init__(self, port=None):
    super(BarcodeScanner,self).__init__(port, BAUDRATE)

  @serial_wrapper
  def read(self, timeout=None):
    """ Read barcode from scanner

      This function expects the scanner to be configured to have the prefix '\xff' followed by a single character code id.
      The function also expects the data to have a null terminated suffix.  These both help frame the data and know what the source was.
    """

    if timeout:
      self.serial.timeout = timeout
    try:
      while read_timeout_ex(self.serial) != '\xff':
        pass
      bc_type = read_timeout_ex(self.serial)
      bc_data = ""
      while True:
        c = read_timeout_ex(self.serial)
        if c == '\0':
          return (bc_type, bc_data)
        else:
          bc_data += c
    except ReadTimeout:
      return None




if __name__ == "__main__":
  import sys
  with BarcodeScanner(sys.argv[1]) as scanner:
    while True:
      data = scanner.read()
      if data:
        print repr(data)


