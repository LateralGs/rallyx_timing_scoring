from serial import Serial, SerialException

def serial_wrapper(func):
  def wrapper(self, *args, **kwargs):
    try:
      if self.is_open():
        return func(self, *args, **kwargs)
    except SerialException:
      self.close()
  return wrapper

class SerialHandler(object):
  def __init__(self, port=None, baudrate=9600):
    self.serial = None
    self.baudrate = baudrate
    self.open(port)

  def open(self, port, baudrate=None, raise_ex=False):
    """ Opens or reopens a serial device """
    if port is None:
      return
    if baudrate is not None:
      self.baudrate = baudrate
    self.close()
    try:
      self.serial = Serial(port=port, baudrate=self.baudrate, timeout=0.1)
    except SerialException:
      if raise_ex:
        raise
      else:
        return False
    else:
      return True

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


