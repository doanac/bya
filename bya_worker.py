#!/usr/bin/python3

import argparse
import fcntl
import json
import logging
import os
import platform
import random
import string
import sys
import urllib.parse

from configparser import ConfigParser
from multiprocessing import cpu_count

import requests

script = os.path.abspath(__file__)
config_file = os.path.join(os.path.dirname(script), 'settings.conf')
config = ConfigParser()
config.read([config_file])

logging.basicConfig(
    level=getattr(logging, config.get('bya', 'log_level', fallback='INFO')))
log = logging.getLogger('bya-worker')


def _create_conf(server_url, version):
    config.add_section('bya')
    config['bya']['server_url'] = server_url
    config['bya']['version'] = version
    config['bya']['log_level'] = 'INFO'
    chars = string.ascii_letters + string.digits + '!@#$^&*~'
    config['bya']['host_api_key'] =\
        ''.join(random.choice(chars) for _ in range(32))
    with open('/etc/hostname') as f:
        config['bya']['hostname'] = f.read().strip()
    with open(config_file, 'w') as f:
        config.write(f, True)


class HostProps(object):
    CACHE = os.path.join(os.path.dirname(script), 'hostprops.cache')

    def __init__(self):
        mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        distro, release, _ = platform.dist()
        self.data = {
            'cpu_total': cpu_count(),
            'cpu_type': platform.processor(),
            'mem_total': mem,
            'distro': '%s %s' % (distro, release),
            'api_key': config['bya']['host_api_key'],
            'name': config['bya']['hostname'],
        }

    def cache(self):
        with open(self.CACHE, 'w') as f:
            json.dump(self.data, f)


class BYAServer(object):
    CRON_FILE = '/etc/cron.d/bya_worker'

    def _post(self, resource, data):
        url = urllib.parse.urljoin(config.get('bya', 'server_url'), resource)
        r = requests.post(url, json=data)
        if r.status_code != 201:
            log.error('Failed to issue request: %s\n' % r.text)
            sys.exit(1)

    def create_host(self, hostprops):
        self._post('/api/v1/host/', hostprops)


def cmd_register(args):
    '''Register this host with the configured BYA server'''
    _create_conf(args.server_url, args.version)
    p = HostProps()
    args.server.create_host(p.data)
    p.cache()
    if not args.no_cron:
        with open(args.server.CRON_FILE, 'w') as f:
            f.write('* * * * *	root %s check\n' % script)


def cmd_uninstall(args):
    '''Remove worker installation'''
    os.unlink(args.server.CRON_FILE)
    os.unlink(config_file)
    os.unlink(script)
    os.rmdir(os.path.dirname(script))


def main(args):
    if getattr(args, 'func', None):
        log.debug('running: %s', args.func.__name__)
        args.func(args)


def get_args(args=None):
    parser = argparse.ArgumentParser('Worker API to BYA server')
    sub = parser.add_subparsers(help='sub-command help')

    p = sub.add_parser('register', help='Register this host with the server')
    p.set_defaults(func=cmd_register)
    p.add_argument('--no-cron', action='store_true',
                   help='Do not create a cron.d entry for this install')
    p.add_argument('server_url')
    p.add_argument('version')

    p = sub.add_parser('uninstall', help='Uninstall the client')
    p.set_defaults(func=cmd_uninstall)

    args = parser.parse_args(args)
    args.server = BYAServer()
    return args


if __name__ == '__main__':
    # Ensure no other copy of this script is running
    with open('/tmp/bya_worker.lock', 'w+') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            log.debug('Script is already running')
            sys.exit(0)
        global lockfile
        lockfile = f
        main(get_args())
