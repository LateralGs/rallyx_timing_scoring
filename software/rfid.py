from serial import Serial, SerialException
from time import sleep

BAUDRATE = 9600

# for use with the RDM6300 or compatible 125khz rfid readers
# RTS is tied to LED (0 = on, 1 = off)
# TX is tied to piezo speaker, optimal tone byte is 0b11001100
# serial settings are 9600,N,8,1

class SerialRFID(object):
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
    self.serial.setRTS(1)


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
    """ Read and parse card id from serial port """
    try:
      if self.is_open():
        c = self.serial.read(1)
        while c != '':
          self.line_buffer = self.line_buffer[-13:] + c
          if len(self.line_buffer) == 14 and self.line_buffer[0] == chr(2) and self.line_buffer[-1] == chr(3):
            # frame matches lets parse the packet
            checksum = int(self.line_buffer[11:13], 16)
            number = self.line_buffer[1:11]
            local_checksum = int(number[0:2],16)
            local_checksum ^= int(number[2:4],16)
            local_checksum ^= int(number[4:6],16)
            local_checksum ^= int(number[6:8],16)
            local_checksum ^= int(number[8:10],16)

            if checksum == local_checksum:
              self.line_buffer = ""
              return int(number,16)

          c = self.serial.read(1)
    except SerialException:
      self.close()

  def notify(self):
    if self.is_open():
      self.serial.setRTS(0)
      self.serial.write(chr(0b11001100)*100)
      sleep(0.2)
      self.serial.setRTS(1)



