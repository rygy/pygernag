#!/usr/bin/env python

import logging
import json
import requests

from random import randint

SUBDOMAIN = ''
API_ACCESS_KEY = ''
NAGIOS_API = ''


def _json_dump(i):
    return json.dumps(i, indent=2, sort_keys=True)


def get_incidents():
    headers = {
        'Authorization': 'Token token={0}'.format(API_ACCESS_KEY),
        'Content-type': 'application/json',
    }

    payload = {
        'status': 'resolved,triggered,acknowledged',
    }

    r = requests.get(
        'https://{0}.pagerduty.com/api/v1/incidents'.format(SUBDOMAIN),
        headers=headers,
        params=payload,
    )

    pd_incidents = json.dumps(r.json(), indent=2, sort_keys=True)
    pd_incidents_json = json.loads(pd_incidents)

    pd_incident_list_nag_trigger = []

    for incident in pd_incidents_json['incidents']:
        #print _json_dump(incident)
        print incident['incident_number']
        if incident['trigger_type'] == 'nagios_trigger':
            pd_incident_list_nag_trigger.append(incident)
    print 'Number of Icidents: ', len(pd_incidents_json['incidents'])

    r_nagios = requests.get('{0}/state'.format(NAGIOS_API))
    ff = json.loads(r_nagios.text)
    #print _json_dump(ff)
    current_problems, no_ack_nag, betwixt = [], [], []

    for host, items in ff['content'].items():
        s_host = items['services']
        for key, val in s_host.items():
            if int(val['current_state']) != 0:
                val['service'] = key
                val['host'] = host
                current_problems.append(val)

    for incident in current_problems:
        if int(incident['problem_has_been_acknowledged']) == 0:
            no_ack_nag.append(incident)

    for item in no_ack_nag:
        for pd_item in pd_incident_list_nag_trigger:
            if (item['service'] in pd_item['incident_key']) is True:
                key = randint(0, 10000)
                item['key'], pd_item['key'] = key, key

                betwixt.append(item)
                betwixt.append(pd_item)

    print 'Results:\n\n', _json_dump(betwixt)

if __name__ == '__main__':
    get_incidents()
