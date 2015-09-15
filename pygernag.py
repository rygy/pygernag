#!/usr/bin/env python

import argparse
import json
import logging
import os
import requests

from random import randint


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


def get_incidents():

    logger = _logger()
    args = _get_args()

    API_ACCESS_KEY = args.pagerduty_api_key
    SUBDOMAIN = args.pagerduty_domain
    NAGIOS_API = args.nagios_api

    # Check Nagios first
    r_nagios = requests.get('http://{0}/state'.format(NAGIOS_API))
    ff = json.loads(r_nagios.text)

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
            logger.warning('Incident Unacknowledged: \n {0}'
                           .format(_json_dump(incident)))
            no_ack_nag.append(incident)

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
        if incident['trigger_type'] == 'nagios_trigger':
            pd_incident_list_nag_trigger.append(incident)

    for item in no_ack_nag:
        for pd_item in pd_incident_list_nag_trigger:
            if (item['service'] in pd_item['incident_key']) is True:
                key = randint(0, 10000)
                item['key'], pd_item['key'] = key, key

                betwixt.append(item)
                betwixt.append(pd_item)

    logger.warning('Matches between Nagios and PD: \n {0}'
                   .format(_json_dump(betwixt)))


if __name__ == '__main__':
    get_incidents()
