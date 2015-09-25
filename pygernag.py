#!/usr/bin/env python

import argparse
import json
import logging
import os
import requests


def _logger():
    """
    Basic logger.
    """

    log = logging.getLogger()
    log.setLevel(logging.WARNING)
    log.addHandler(logging.StreamHandler())

    return log


def _get_args():
    """
    Required input:
        pagerduty-domain
        pagerduty api-key
        nagios api endpoint
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

    return parser


def _json_dump(i):
    """
    pretty.
    """

    return json.dumps(i, indent=2, sort_keys=True)


def ack_alert(host, nagios_api, service=None):
    """
    Acknowledge a problem in Nagios.
    Specify service AND host if ack --> service.
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

    req = requests.post(
        'http://{0}/acknowledge_problem'.format(nagios_api),
        headers=headers,
        json=payload
        )

    return req


def nag_pd_sync_services(args, logger):
    """
    sync acks from PD back to Nagios.
    """

    pd_api_key = args.pagerduty_api_key
    pd_subdomain = args.pagerduty_domain
    nagios_api = args.nagios_api

    r_nagios = requests.get('http://{0}/state'.format(nagios_api))
    ff = json.loads(r_nagios.text)

    current_problems, no_ack_nag = [], []

    for host, items in ff['content'].items():
        s_host = items['services']
        for key, val in s_host.items():
            if int(val['current_state']) != 0:
                val['service'] = key
                val['host'] = host
                current_problems.append(val)

    for problem in current_problems:
        if int(problem['problem_has_been_acknowledged']) == 0:
            if int(problem['active_checks_enabled']) == 1:
                problem['nagios_service'] = problem['service']
                no_ack_nag.append(problem)

    if not no_ack_nag:
        logger.warning('No current Nagios problems!')
        os.sys.exit(0)
    if no_ack_nag:
        logger.warning('Nagios problems found:\t {0}'
                       .format(len(no_ack_nag)))

    headers = {
        'Authorization': 'Token token={0}'.format(pd_api_key),
        'Content-type': 'application/json',
    }

    payload = {
        'status': 'triggered,acknowledged',
    }

    r = requests.get(
        'https://{0}.pagerduty.com/api/v1/incidents'.format(pd_subdomain),
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
    ack_in_nagios = None
    for problem in problems:
        if problem['status'] == 'acknowledged':
            if int(problem['problem_has_been_acknowledged']) == 0:
                ack_in_nagios = ack_alert(
                    problem['host'],
                    nagios_api,
                    service=problem['nagios_service']
                )

    if ack_in_nagios:
        logger.warning(ack_in_nagios.json())

if __name__ == '__main__':

    nag_log = _logger()
    nag_args = _get_args().parse_args()

    if None in nag_args.__dict__.values():
        nag_log.warning(_get_args().print_help())
        os.sys.exit(1)

    nag_pd_sync_services(nag_args, nag_log)
