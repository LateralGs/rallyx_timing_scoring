import urllib2
import json
from pprint import pprint

MSREG_ORG_ID = 'FF21EB64-022B-A56D-C1065D1C90806B4B'

event_list = json.load(urllib2.urlopen('https://api.motorsportreg.com/rest/calendars/organization/%s.json?archive=true' % MSREG_ORG_ID))['response']['events']

for event in event_list:
  pprint(event)
  driver_list = json.load(urllib2.urlopen('https://api.motorsportreg.com/rest/index.cfm/events/%s/entrylist.json' % event['id']))['response']['assignments']
  for driver in driver_list:
    print driver['firstName'], driver['lastName']
