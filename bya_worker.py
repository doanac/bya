#!/usr/bin/python3

import argparse
import fcntl
import json
import logging
import os
import platform
import random
import shutil
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


def _create_conf(server_url, version, concurrent_runs, host_tags):
    config.add_section('bya')
    config['bya']['server_url'] = server_url
    config['bya']['version'] = version
    config['bya']['log_level'] = 'INFO'
    config['bya']['concurrent_runs'] = str(concurrent_runs)
    config['bya']['host_tags'] = host_tags
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
        self.data = {
            'cpu_total': cpu_count(),
            'cpu_type': platform.processor(),
            'mem_total': mem,
            'distro': self._get_distro(),
            'api_key': config['bya']['host_api_key'],
            'name': config['bya']['hostname'],
            'concurrent_runs': int(config['bya']['concurrent_runs']),
            'host_tags': config['bya']['host_tags'],
        }

    def _get_distro(self):
        with open('/etc/os-release') as f:
            for line in f:
                if line.startswith('PRETTY_NAME'):
                    return line.split('=')[1].strip().replace('"', '')
        return '?'

    def cache(self):
        with open(self.CACHE, 'w') as f:
            json.dump(self.data, f)

    def update_if_needed(self, server):
        try:
            with open(self.CACHE) as f:
                cached = json.load(f)
        except:
            cached = {}
        if cached != self.data:
            log.info('updating host properies on server: %s', self.data)
            server.update_host(self.data)
            self.cache()


class Runner(object):
    RUNS_DIR = os.path.join(os.path.dirname(script), 'runs')

    @classmethod
    def get_num_available(clazz):
        '''Return the number of available runners we have'''
        active = 0
        if os.path.exists(clazz.RUNS_DIR):
            active = len(os.listdir(clazz.RUNS_DIR))
        avail = int(config['bya']['concurrent_runs']) - active
        if avail < 0:
            log.error('Number of concurrent runs seems to be > max configured')
        return avail

    @classmethod
    def execute(run):
        raise NotImplementedError()


class BYAServer(object):
    CRON_FILE = '/etc/cron.d/bya_worker'

    def __init__(self):
        self.requests = requests

    def _auth_headers(self):
        return {
            'content-type': 'application/json',
            'Authorization': 'Token ' + config['bya']['host_api_key'],
        }

    def _get(self, resource, params=None):
        url = urllib.parse.urljoin(config['bya']['server_url'], resource)
        r = self.requests.get(url, params=params, headers=self._auth_headers())
        if r.status_code != 200:
            log.error('Failed to issue request: %s\n' % r.text)
            sys.exit(1)
        return r

    def _post(self, resource, data):
        url = urllib.parse.urljoin(config['bya']['server_url'], resource)
        r = self.requests.post(url, json=data)
        if r.status_code != 201:
            log.error('Failed to issue request: %s\n' % r.text)
            sys.exit(1)

    def _patch(self, resource, data):
        url = urllib.parse.urljoin(config['bya']['server_url'], resource)
        r = self.requests.patch(url, json=data, headers=self._auth_headers())
        if r.status_code != 200:
            log.error('Failed to issue request: %s\n' % r.text)
            sys.exit(1)

    def _delete(self, resource):
        url = urllib.parse.urljoin(config['bya']['server_url'], resource)
        r = self.requests.delete(url, headers=self._auth_headers())
        if r.status_code != 200:
            log.error('Failed to issue request: %s\n' % r.text)
            sys.exit(1)

    def create_host(self, hostprops):
        self._post('/api/v1/host/', hostprops)

    def update_host(self, hostprops):
        self._patch('/api/v1/host/%s/' % config['bya']['hostname'], hostprops)

    def delete_host(self):
        self._delete('/api/v1/host/%s/' % config['bya']['hostname'])

    def check_in(self, num_available):
        params = {'available_runners': num_available}
        return self._get(
            '/api/v1/host/%s/' % config['bya']['hostname'], params).json()

    def get_worker_script(self):
        return self._get('/bya_worker.py').text


def cmd_register(args):
    '''Register this host with the configured BYA server'''
    _create_conf(
        args.server_url, args.version, args.concurrent_runs, args.host_tags)
    p = HostProps()
    args.server.create_host(p.data)
    p.cache()
    if not args.no_cron:
        with open(args.server.CRON_FILE, 'w') as f:
            f.write('* * * * *	root %s check\n' % script)


def cmd_uninstall(args):
    '''Remove worker installation'''
    args.server.delete_host()
    shutil.rmtree(os.path.dirname(script))


def _upgrade_worker(args, version):
    buf = args.server.get_worker_script()
    with open(__file__, 'wb') as f:
        f.write(buf.encode())
        f.flush()
    config['bya']['version'] = version
    with open(config_file, 'w') as f:
        config.write(f, True)
    os.execv(script, [script, 'check'])


def cmd_check(args):
    '''Check in with server for work'''
    HostProps().update_if_needed(args.server)
    c = args.server.check_in(Runner.get_num_available())
    if c['worker_version'] != config['bya']['version']:
        log.warning('Upgrading client to: %s', c['worker_version'])
        _upgrade_worker(args, c['worker_version'])
    for run in c.get('runs', []):
        Runner.execute(run)


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
    p.add_argument('--concurrent-runs', type=int, default=2,
                   help='Maximum number of current runs. Default=%(default)d')
    p.add_argument('server_url')
    p.add_argument('version')
    p.add_argument('host_tags', help='Comma separated list')

    p = sub.add_parser('uninstall', help='Uninstall the client')
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser('check', help='Check in with server for updates')
    p.set_defaults(func=cmd_check)

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
