from serial import Serial, SerialException
from time import sleep

class DriverLicenseScanner(object):
  def __init__(self, port=None):
    self.serial = None
    self.line_buffer = ""
    self.open(port)


  def open(self, port):
    """ Opens or reopens a serial device """
    if port is None:
      return
    self.close()
    self.serial = Serial(port=port, timeout=0.1)


  def is_open(self):
    return self.serial is not None and self.serial.is_open


  def close(self):
    if self.is_open():
      self.serial.close()
    self.serial = None


  def __enter__(self):
    return self


  def __exit__(self, exc_type, exc_value, traceback):
    self.close()


  def read_card(self):
    try:
      if self.is_open():
        c = self.serial.read(1)
        while c != '':
          self.line_buffer += c
          # TODO FIXME

          c = self.serial.read(1)
    except SerialException:
      self.close()


