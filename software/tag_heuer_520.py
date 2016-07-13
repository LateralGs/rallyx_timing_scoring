import logging
logging.basicConfig()
from serial_handler import SerialHandler, serial_wrapper

BAUDRATE = 9600

class TagHeuer520(SerialHandler):
  def __init__(self, port=None):
    super(TagHeuer520,self).__init__(port,BAUDRATE)
    self.line_buffer = ""

  @serial_wrapper
  def read(self):
    """ Read and parse time from serial port """
    c = self.serial.read(1)
    while c != '':
      if c == '\r':
        logging.debug(repr(self.line_buffer))
        result = None
        # TODO add ability to handle other types of time events eg. T-, T+, etc.
        if self.line_buffer.startswith('T ') and len(self.line_buffer) == 30:
          channel = self.line_buffer[12:14].strip()
          time_ms = 0
          try:
            if self.line_buffer[15:17].strip() != '':
                time_ms += (60*60*1000) * int(self.line_buffer[15:17])
            if self.line_buffer[18:20].strip() != '':
                time_ms += (60*1000) * int(self.line_buffer[18:20])
            time_ms += 1000 * int(self.line_buffer[21:23])
            time_ms += int(self.line_buffer[24:27])
          except ValueError:
            self.line_buffer = ""
            return None
          result = (channel, time_ms)
        else:
            logging.debug('bad time event format')
        self.line_buffer = ""
        return result
      else:
        self.line_buffer += c
      c = self.serial.read(1)
    return None


if __name__ == "__main__":
  import sys
  timer = TagHeuer520(sys.argv[1])
  while True:
    t = timer.read()
    if t:
      print t

