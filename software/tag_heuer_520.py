from serial import Serial, SerialException
from datetime import timedelta
import sys

BAUDRATE = 9600

class TagHeuer520(object):
  def __init__(self, port=None):
    self.serial = None
    self.line_buffer = ""
    self.open(port)


  def open(self, port):
    """ Opens or reopens a serial device """
    if port is None:
      return
    self.close()
    self.serial = Serial(port=port, baudrate=BAUDRATE, timeout=0.1)


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


  def read_time(self):
    """ Read and parse time from serial port """
    try:
      if self.is_open():
        c = self.serial.read(1)
        while c != '':
          if c == '\r':
            result = None
            if self.line_buffer.startswith('T ') and len(self.line_buffer) == 30:
              channel = self.line_buffer[12:14].strip()
              try:
                h = int(self.line_buffer[15:17])
              except ValueError:
                h = 0
              try:
                m = int(self.line_buffer[18:20])
              except ValueError:
                m = 0
              try:
                s = float(self.line_buffer[21:])
              except ValueError:
                s = 0
              result = (channel, timedelta(hours=h, minutes=m, seconds=s))
            self.line_buffer = ""
            return result
          else:
            self.line_buffer += c
          c = self.serial.read(1)
    except SerialException:
      self.close()



if __name__ == "__main__":
  timer = TagHeuer520(sys.argv[1])
  prev_start = 0
  prev_finish = 0
  timer_dust_window = 10
  try:
    while timer.is_open():
      t = timer.read_time()
      if t is not None:
        if t[0] in ('1','M1'):
          if t[1].total_seconds() > (prev_start + timer_dust_window):
            print "START -> %s (%s)" % (t[1], t[1].total_seconds())
            prev_start = t[1].total_seconds()
          else:
            print "START DUST WINDOW"
        elif t[0] in ('2','M2'):
          if t[1].total_seconds() > (prev_finish + timer_dust_window):
            print "FINISH -> %s (%s)" % (t[1], t[1].total_seconds())
            prev_finish = t[1].total_seconds()
          else:
            print "FINISH DUST WINDOW"
  except KeyboardInterrupt:
    pass

