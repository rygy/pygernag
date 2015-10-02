#!/usr/bin/env python

import argparse
import json
import logging
import os
import requests

from requests.exceptions import ConnectionError


def _logger(log_file=None):
    """
    Basic logger.
    """

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    else:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


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
                        .pagerduty.com bit \
                         - Defaults to env(PAGERDUTY_DOMAIN)',
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
    parser.add_argument('--log-file',
                        help='Log output to file',
                        default=os.environ.get('PYGERNAG_LOG', None)
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

    try:
        r_nagios = requests.get('http://{0}/state'.format(nagios_api))
    except ConnectionError:
        logger.error('Unable to contact Nagios API: {0} - Exiting'.format(nagios_api))
        os.sys.exit(1)

    ff = json.loads(r_nagios.text)

    service_problems, host_problems, no_ack_nag = [], [], []

    for host, items in ff['content'].items():
        if int(items['current_state']) != 0:
            if int(items['problem_has_been_acknowledged']) == 0:
                host_problems.append(host)
        s_host = items['services']
        for key, val in s_host.items():
            if int(val['current_state']) != 0:
                val['service'] = key
                val['host'] = host
                service_problems.append(val)

    for problem in service_problems:
        if int(problem['problem_has_been_acknowledged']) == 0:
            if int(problem['active_checks_enabled']) == 1:
                problem['nagios_service'] = problem['service']
                no_ack_nag.append(problem)

    if not no_ack_nag:
        logger.warn('No current Nagios service problems found')
    if no_ack_nag:
        logger.warn('Nagios service problems found:\t {0}'
                       .format(len(no_ack_nag)))
    if not host_problems:
        logger.warn('No current Nagios host problems found')
    if host_problems:
        logger.warn('Nagios host problems found: \t {0}'
                       .format(len(host_problems)))

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

    service_problems = []

    # Match service problems in Nagios to PD Incidents
    for item in no_ack_nag:
        for pd_item in pd_incident_list_nag_trigger:
            if (item['host'] in pd_item['incident_key']) is True:
                temp = item.copy()
                temp.update(pd_item)

                service_problems.append(temp)

    if service_problems:
        logger.warn('Matches Found: {0}'.format(_json_dump(service_problems)))

    ack_in_nagios, ack_in_nagios_host = None, None

    # Check service problems for an acknowledgment
    # and ack back in Nagios where appropriate

    for problem in service_problems:
        if problem['status'] == 'acknowledged':
            if int(problem['problem_has_been_acknowledged']) == 0:
                ack_in_nagios = ack_alert(
                    problem['host'],
                    nagios_api,
                    service=problem['nagios_service']
                )
                logger.warn('Acknowledging Service problem in Nagios')
                logger.warn(ack_in_nagios.json())

    # Do the same for Host problem alerts
    for host in host_problems:
        for pd_item in pd_incident_list_nag_trigger:
            if host == pd_item['trigger_summary_data']['HOSTNAME']:
                ack_in_nagios_host = ack_alert(host, nagios_api)
                logger.warn('Acknowledging Host problem in Nagios')
                logger.warn(ack_in_nagios_host.json())


def main():

    nag_args = _get_args().parse_args()
    nag_log = _logger(nag_args.log_file)

    if None in nag_args.__dict__.values()[1:]:
        nag_log.warning(_get_args().print_help())
        os.sys.exit(1)

    nag_pd_sync_services(nag_args, nag_log)


if __name__ == '__main__':
    main()
