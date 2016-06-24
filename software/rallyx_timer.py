import logging
from serial_handler import SerialHandler, serial_wrapper

class RallyXTimer(SerialHandler):
  def __init__(self, port=None):
    super(RallyXTimer,self).__init__(port)
    self.debounce = None
    self.deadtime = None
    self.sequence_num = None
    self.time_ms = None
    self.time_str = None
    self.channel = None
    self.line_buffer = ""
    self.log = logging.getLogger(__name__)

  @serial_wrapper
  def set_deadtime(self, value):
    self.serial.write("deadtime %d\r\n" % value)
  
  @serial_wrapper
  def set_debounce(self, value):
    self.serial.write("debounce %d\r\n" % value)
  
  @serial_wrapper
  def set_time(self, value):
    self.serial.write("time %d\r\n" % value)

  @serial_wrapper
  def read(self):
    """ Read and parse time from serial port """
    c = self.serial.read(1)
    while c != '':
      if c not in "\r\n":
        self.line_buffer += c
      elif len(self.line_buffer) > 0:
        self.log.debug(self.line_buffer)
        args = self.line_buffer.split()
        self.line_buffer = ""
        if len(args) == 4 and args[0] == 'T':
          self.channel = args[1]
          try:
            self.time_ms = int(args[2])
          except ValueError:
            self.time_ms = None
          try:
            self.sequence_num = int(args[3])
          except ValueError:
            self.sequence_num = None
          return (self.channel, self.time_ms)
        elif len(args) == 2 and args[0] == 'D':
          try:
            self.deadtime = int(args[1])
          except ValueError:
            self.deadtime = None
        elif len(args) == 2 and args[0] == 'B':
          try:
            self.debounce = int(args[1])
          except ValueError:
            self.debounce = None
        else:
          self.log.debug(args)
      c = self.serial.read(1)

