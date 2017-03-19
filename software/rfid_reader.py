from serial_handler import SerialHandler, serial_wrapper
import re

BAUDRATE = 9600

# for use with the RDM6300 or compatible 125khz rfid readers
# RTS is tied to LED (0 = on, 1 = off)
# TX is tied to piezo speaker, optimal tone byte is 0b11001100
# serial settings are 9600,N,8,1

class RFIDReader(SerialHandler):
  def __init__(self, port=None):
    super(RFIDReader,self).__init__(port, BAUDRATE)
    self.line_buffer = ""
    self.version_id = None
    self.serial_number = None

  @serial_wrapper
  def read(self):
    """ Read and parse card id from serial port """
    c = self.serial.read(1)
    while c != '':
      self.line_buffer = self.line_buffer[-13:] + c
      if re.match("^\x02[0-9a-fA-F]{12}\x03$",self.line_buffer):
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
          self.version_id = int(number[0:2],16)
          self.serial_number = int(number[2:10],16)
          return self.serial_number
      c = self.serial.read(1)
    return None

  @serial_wrapper
  def send_ack(self):
    self.serial.write('a')

  @serial_wrapper
  def beep(self, count=1):
    self.serial.write('b' * count)
  
  @serial_wrapper
  def pause(self, count=1):
    self.serial.write('p' * count)

  @serial_wrapper
  def quiet_mode(self):
    self.serial.write('q')


if __name__ == "__main__":
  import sys
  with RFIDReader(sys.argv[1]) as reader:
    while True:
      data = reader.read()
      if data:
        reader.send_ack()
        reader.pause(2)
        reader.beep(2)
        print repr(data), repr([reader.version_id,reader.serial_number])

