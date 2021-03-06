import subprocess
import logging
import json
import urllib2
import os
import types
import re
from datetime import date

# used to pipe stdout from subprocess to /dev/null
dev_null = open(os.devnull, 'wb')
util_log = logging.getLogger(__name__)


def date_weekday(date_str):
  try:
    return date(*map(int,date_str.split('-'))).strftime('%A')
  except:
    return None

#######################################

def play_sound(path):
  # this uses the play command provided by the sox package
  # using Popen allows this to be non blocking
  try:
    subprocess.Popen(['play',path], stdout=dev_null, stderr=dev_null)
  except Exception as e:
    util_log.error(e)

#######################################

def print_label(printer, text, lpi=None, cpi=None, nowrap=False):
  # use CUPS lp command to print plain text
  try:
    args = ['lp','-d',printer]
    if lpi:
      args += ['-o', 'lpi=%d' % lpi]
    if cpi:
      args += ['-o', 'cpi=%d' % cpi]
    if nowrap:
      args += ['-o', 'nowrap']
    util_log.debug(args)
    proc = subprocess.Popen(args,stdin=subprocess.PIPE, stdout=dev_null, stderr=dev_null)
    proc.stdin.write(text)
    proc.stdin.close()
  except Exception as e:
    util_log.error(e)

#######################################

def json_query(url):
  return json.load(urllib2.urlopen(url))

#######################################

def parse_time_ex(time_str):
  if time_str is None:
    return None
  if not isinstance(time_str, types.StringTypes):
    raise TypeError()
  time_str = time_str.strip()
  if time_str == '':
    return None
  match = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d{0,3}))?$", time_str)
  if match:
    h, m, s, ms = match.groups()
    time_ms = 0
    time_ms += int(h) * (60 * 60 * 1000)
    time_ms += int(m) * (60 * 1000)
    time_ms += int(s) * (1000)
    if ms:
      time_ms += int(ms + ('0' * (3-len(ms))))
    return time_ms
  match = re.match(r"^(\d+):(\d{1,2})(?:\.(\d{0,3}))?$", time_str)
  if match:
    m, s, ms = match.groups()
    time_ms = 0
    time_ms += int(m) * (60 * 1000)
    time_ms += int(s) * (1000)
    if ms:
      time_ms += int(ms + ('0' * (3-len(ms))))
    return time_ms
  match = re.match(r"^(\d+)(?:\.(\d{0,3}))?$", time_str)
  if match:
    s, ms = match.groups()
    time_ms = 0
    time_ms += int(s) * (1000)
    if ms:
      time_ms += int(ms + ('0' * (3-len(ms))))
    return time_ms
  raise ValueError()

#######################################

def format_time(time_ms, hms=True):
  prefix = ''

  if isinstance(time_ms, types.StringTypes):
    time_ms = parse_int(time_ms, None)

  if time_ms is None:
    return ""

  if time_ms < 0:
    time_ms = -time_ms
    prefix = '-'
  
  if hms:
    ms = time_ms % 1000
    s = (time_ms / 1000) % 60
    m = (time_ms / (60 * 1000)) % 60
    h = time_ms / (60 * 60 * 1000)
    if h > 0:
      return "%s%d:%02d:%02d.%03d" % (prefix,h,m,s,ms)
    elif m > 0:
      return "%s%d:%02d.%03d" % (prefix,m,s,ms)
    else:
      return "%s%d.%03d" % (prefix,s,ms)
  else:
    return "%s%d.%03d" % (prefix, time_ms / 1000, time_ms % 1000)

#######################################

def pad(s):
  return s.replace(' ', '&nbsp;')

#######################################

def parse_int(num_str, default=None):
  try:
    return int(num_str)
  except ValueError:
    return default
  except TypeError:
    return default

#######################################

def clean_str(s):
  if isinstance(s,types.StringTypes):
    s = s.strip()
    if s == '':
      return None
    else:
      return s
  else:
    return s

#######################################

def time_cmp(a,b):
  #util_log.debug("time_cmp: %r, %r", a, b)
  if a is None and b is None:
    return 0
  elif a is None:
    return 1
  elif b is None:
    return -1
  elif a < b:
    return -1
  elif a > b:
    return 1
  else:
    return 0

#######################################

def run_cmp(a,b):
  #util_log.debug("run_cmp: %r, %r", a, b)
  if a['dns_dnf'] and b['dns_dnf']:
    return 0
  elif a['dns_dnf']:
    return 1
  elif b['dns_dnf']:
    return -1
  elif a['total_time_ms'] in (0,None) and b['total_time_ms'] in (0,None):
    return 0
  elif a['total_time_ms'] in (0,None):
    return 1
  elif b['total_time_ms'] is (0,None):
    return -1
  elif a['total_time_ms'] < b['total_time_ms']:
    return -1
  elif a['total_time_ms'] > b['total_time_ms']:
    return 1
  else:
    return 0

#######################################

def entry_cmp(a,b):
  #util_log.debug("entry_cmp: %r, %r", a, b)
  if a['event_runs'] < b['event_runs']:
    return 1
  elif a['event_runs'] > b['event_runs']:
    return -1
  elif a['event_time_ms'] in (0,None) and b['event_time_ms'] in (0,None):
    return 0
  elif a['event_time_ms'] in (0,None):
    return 1
  elif b['event_time_ms'] in (0,None):
    return -1
  elif a['event_time_ms'] < b['event_time_ms']:
    return -1
  elif a['event_time_ms'] > b['event_time_ms']:
    return 1
  else:
    return 0

def start_entry_cmp(a,b):
  if a['run_count'] < b['run_count']:
    return 1
  elif a['run_count'] > b['run_count']:
    return -1
  else:
    return 0
