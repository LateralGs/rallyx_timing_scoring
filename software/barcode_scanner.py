from serial_handler import SerialHandler, serial_wrapper
import re
from cStringIO import StringIO

BAUDRATE = 9600

class ReadTimeout(Exception):
  pass


def read_timeout_ex(s,n=1):
  s = s.read(n)
  if s == '':
    raise ReadTimeout()
  else:
    return s


def decode_license(data):
  """ Decode US Drivers License from a PDF417 barcode """
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
  def read(self, timeout=1):
    # use the fact that we can poll the scanner faster than it will return sequential barcodes
    # we can then use the timeout to frame the input data
    self.serial.timeout = timeout
    barcode = self.serial.read()
    if len(barcode) > 0:
      return barcode
    else:
      return None


if __name__ == "__main__":
  import sys
  with BarcodeScanner(sys.argv[1]) as scanner:
    while True:
      data = scanner.read()
      if data:
        print repr(data)


