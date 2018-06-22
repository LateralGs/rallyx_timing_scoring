from __future__ import print_function

import subprocess as sp
import os
import re
from glob import glob
import signal
from time import sleep
from configparser import ConfigParser

config_defaults = {
  'host_ip': '10.10.10.10',
  'interface': '',
  'iface_glob': '/sys/class/net/wlan*',
  'ssid': 'rallyx_scoring'
  }

# handle_probe_req: send failed
# Failed to set beacon parameters
re_bad_line = re.compile("(handle_probe_req: send failed|Failed to set beacon parameters)")

if __name__ == "__main__":
  # load configuration
  config = ConfigParser()
  config.add_section('config')
  for key,value in config_defaults.items():
    config.set('config',key,value)
  config.read("ap_config.ini")

  if config.get('config','interface').strip() == '':
    print("Searching for iface_glob")
    path_list = glob(config.get('config','iface_glob'))
    if len(path_list) == 0:
      raise Exception("No wireless interface specified or found via iface_glob")
    # default to first interface found
    iface = os.path.basename(path_list[0])
    config.set('config','interface',iface)

  # start create_ap subprocess
  create_ap_args = ['create_ap']
  create_ap_args.append('-n')
  create_ap_args.append('--redirect-to-localhost')
  create_ap_args.append('--isolate-clients')
  create_ap_args.append('-g')
  create_ap_args.append(config.get('config', 'host_ip'))
  create_ap_args.append(config.get('config', 'interface'))
  create_ap_args.append(config.get('config', 'ssid'))

  run = True

  while run:
    with sp.Popen(create_ap_args, stdout=sp.PIPE, stderr=sp.STDOUT) as p:
      try:
        print("!!!! START !!!!")
        # monitor output for signs we should restart create_ap
        for line in p.stdout:
          line = line.decode('utf8')
          print(line,end='') # line already has newline
          if re_bad_line.match(line):
            print("!!!! STOP -> RESTART !!!!")
            # gracefully exit create_ap
            p.send_signal(signal.SIGUSR1)
            p.wait()
      except KeyboardInterrupt:
        print("!!!! STOP -> INT!!!!")
        # gracefully exit create_ap
        p.send_signal(signal.SIGUSR1)
        p.wait()
        run = False
  print("exiting")



