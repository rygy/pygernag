#!/usr/bin/env python

import argparse
import json
import logging
import os
import requests

from requests.exceptions import ConnectionError


def _logger(log_file=None, level=logging.WARN):
    """
    Basic logger.
    """

    logger = logging.getLogger()
    logger.setLevel(level)
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


def ack_alert(host, nagios_api, comment, service=None):
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
            'service': service,
            'comment': comment
        }
    else:
        payload = {
            'host': host,
            'comment': comment
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

    comment = 'Ack via PD - '

    try:
        r_nagios = requests.get('http://{0}/state'.format(nagios_api))
    except ConnectionError:
        logger.error('Unable to contact Nagios API: {0} - Exiting'.format(nagios_api))
        os.sys.exit(1)

    ff = json.loads(r_nagios.text)

    service_problems, host_problems = [], []

    for host, items in ff['content'].items():
        if int(items['current_state']) != 0:
            if int(items['problem_has_been_acknowledged']) == 0:
                if int(items['active_checks_enabled']) == 1:
                    host_problems.append(host)
        s_host = items['services']
        for key, val in s_host.items():
            if int(val['current_state']) != 0:
                val['service'] = key
                val['host'] = host
                if int(val['problem_has_been_acknowledged']) == 0:
                    if int(items['active_checks_enabled']) == 1:
                        val['nagios_service'] = val['service']
                        service_problems.append(val)

    if not service_problems:
        logger.warn('No current unacknowledged Nagios service problems found')
    if service_problems:
        logger.warn('Unacknowledged Nagios service problems found:\t {0}'
                    .format(len(service_problems)))

    if not host_problems:
        logger.warn('No current unacknowledged Nagios host problems found')
    if host_problems:
        logger.warn('Unacknowledged Nagios host problems found: \t {0}'
                    .format(len(host_problems)))
        logger.warn(_json_dump(host_problems))

    headers = {
        'Authorization': 'Token token={0}'.format(pd_api_key),
        'Content-type': 'application/json',
    }

    payload = {
        'status': 'acknowledged, triggered',
    }

    r = requests.get(
        'https://{0}.pagerduty.com/api/v1/incidents'.format(pd_subdomain),
        headers=headers,
        params=payload,
    )

    pd_incidents = json.dumps(r.json(), indent=2, sort_keys=True)
    pd_incidents_json = json.loads(pd_incidents)

    logger.warn(pd_incidents)

    pd_incident_list_nag_trigger = []

    for incident in pd_incidents_json['incidents']:
        if incident['trigger_type'] == 'nagios_trigger' or 'trigger':
            pd_incident_list_nag_trigger.append(incident)

    service_matches, host_matches = [], []

    # Match service problems in Nagios to PD Incidents
    for item in service_problems:
        for pd_item in pd_incident_list_nag_trigger:
            if (item['host'] in pd_item['incident_key']) is True:
                if (item['nagios_service'] in pd_item['incident_key']) is True:
                    temp = item.copy()
                    temp.update(pd_item)

                    service_matches.append(temp)

    # Match host problems in Nagios to PD Incidents
    for host in host_problems:
        for pd_item in pd_incident_list_nag_trigger:
            try:
                if host == pd_item['trigger_summary_data']['HOSTNAME']:
                    host_matches.append(pd_item)
            except KeyError:
                pass
    if service_matches:
        logger.warn('Matching PD -> Service Nagios Found: {0}'.format(_json_dump(service_matches)))
    if not service_matches:
        logger.warn('No Matching PD -> Service Nagios Incidents found')

    if host_matches:
        logger.warn('Matching PD -> Host Nagios Found: {0}'.format(_json_dump(host_matches)))
    if not host_matches:
        logger.warn('No Matching PD -> Host Nagios Incidents found')

    # Check service problems for an acknowledgment
    # and ack back in Nagios where appropriate
    for problem in service_matches:
        if problem['status'] == 'acknowledged':
            if int(problem['problem_has_been_acknowledged']) == 0:
                ack_in_nagios = ack_alert(
                    problem['host'],
                    nagios_api,
                    comment=comment + problem['html_url'],
                    service=problem['nagios_service']
                )
                logger.warn('Acknowledging Service problem in Nagios')
                logger.warn(ack_in_nagios.json())

    # Do the same for Host problem alerts
    for host in host_problems:
        for pd_item in pd_incident_list_nag_trigger:
            try:
                if host == pd_item['trigger_summary_data']['HOSTNAME']:
                    if pd_item['status'] == 'acknowledged':
                        ack_in_nagios_host = ack_alert(
                            host,
                            nagios_api,
                            comment=comment + pd_item['html_url'])

                        logger.warn('Acknowledging Host problem in Nagios')
                        logger.warn(ack_in_nagios_host.json())
            except KeyError:
                pass


def main():

    nag_args = _get_args().parse_args()
    nag_log = _logger(nag_args.log_file)

    if None in nag_args.__dict__.values()[1:]:
        nag_log.warning(_get_args().print_help())
        os.sys.exit(1)

    nag_pd_sync_services(nag_args, nag_log)


if __name__ == '__main__':
    main()
