#!/usr/bin/env python

import argparse
import json
import logging
import os
import requests


def _logger():
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)
    logger.addHandler(logging.StreamHandler())

    return logger


def _get_args():
    """
    Do some shit.
    """

    parser = argparse.ArgumentParser(usage=__doc__)

    parser.add_argument('--pagerduty-domain',
                        help='Enter your pagerduty domain withouth the \
                        .pagerduty.com bit',
                        default=os.environ.get('PAGERDUTY_DOMAIN', None)
                        )
    parser.add_argument('--pagerduty-api-key',
                        help='Enter your PD API Key',
                        default=os.environ.get('PAGERDUTY_API_KEY', None)
                        )
    parser.add_argument('--nagios-api',
                        help='Enter the API endpoint for Nagios',
                        default=os.environ.get('NAGIOS_API_ENDPOINT', None)
                        )

    args = parser.parse_args()

    return args


def _json_dump(i):
    return json.dumps(i, indent=2, sort_keys=True)


def ack_alert(host, nagios_api, service=None):
    """
    Acknowledge the host / service problem in Nagios.
    """

    headers = {
        'Content-type': 'application/json',
    }

    if service:
        payload = {
            'host': host,
            'service': service
        }
    else:
        payload = {
            'host': host
        }
    print payload
    req = requests.post(
        'http://{0}/acknowledge_problem'.format(nagios_api),
        headers=headers,
        json=payload
        )

    return req


def get_incidents():

    logger = _logger()
    args = _get_args()

    API_ACCESS_KEY = args.pagerduty_api_key
    SUBDOMAIN = args.pagerduty_domain
    NAGIOS_API = args.nagios_api

    r_nagios = requests.get('http://{0}/state'.format(NAGIOS_API))
    ff = json.loads(r_nagios.text)

    current_problems, no_ack_nag = [], []

    for host, items in ff['content'].items():
        s_host = items['services']
        for key, val in s_host.items():
            if int(val['current_state']) != 0:
                val['service'] = key
                val['host'] = host
                current_problems.append(val)

    for incident in current_problems:
        if int(incident['problem_has_been_acknowledged']) == 0:
            if int(incident['active_checks_enabled']) == 1:
                no_ack_nag.append(incident)

    if not no_ack_nag:
        logger.warning('No current Nagios problems!')
        os.sys.exit(0)
    if no_ack_nag:
        logger.warning('Nagios problems found:\t {0}'
                       .format(len(no_ack_nag)))

    headers = {
        'Authorization': 'Token token={0}'.format(API_ACCESS_KEY),
        'Content-type': 'application/json',
    }

    payload = {
        'status': 'triggered,acknowledged',
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
        if incident['trigger_type'] == 'nagios_trigger':
            pd_incident_list_nag_trigger.append(incident)

    problems = []

    for item in no_ack_nag:
        for pd_item in pd_incident_list_nag_trigger:
            if (item['host'] in pd_item['incident_key']) is True:
                temp = item.copy()
                temp.update(pd_item)

                problems.append(temp)

    if problems:
        logger.warning('Matches between Nagios and PD: {0}'
                       .format(_json_dump(problems)))

#    tee = ack_alert('test-mon-001', NAGIOS_API, service='PING-mon-test-001')

#    print tee.json()

if __name__ == '__main__':
    get_incidents()
