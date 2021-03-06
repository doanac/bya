#!/usr/bin/python3

import argparse
import datetime
import fcntl
import logging
import os
import select
import shutil
import subprocess
import sys
import time
import traceback
import urllib.parse

import requests

logging.basicConfig()
log = logging.getLogger('bya-runner')

RUNNER_DIR = os.path.abspath(os.path.dirname(__file__))


def _get_params():
    '''A simple way to make this script easier to mock and test'''
    return os.environ


def _post(url, data, headers, retry=1):
    for x in range(retry):
        r = requests.post(url, headers=headers, data=data)
        if r.status_code == 200:
            return r
        time.sleep(2*x + 1)  # try and give the server a moment
    log.error('Failed to issue request(%s): %s\n' % (url, r.text))
    return False


def _update_run(args, msg, status=None, retry=2):
    resource = ('api/v1/build/' + args.build_name + '/' + args.build_num +
                '/' + args.run + '/')
    url = urllib.parse.urljoin(args.bya_server, urllib.parse.quote(resource))
    headers = {
        'content-type': 'text/plain',
        'Authorization': 'Token ' + args.api_key,
    }
    if status:
        headers['X-BYA-STATUS'] = status
    return _post(url, msg, headers, retry=4)


def _update_status(args, status, msg):
    log.debug('Updating status to: %s : %s', status, msg)
    msg = '== %s: %s\n' % (datetime.datetime.utcnow(), msg)
    if not _update_run(args, msg, status, 4):
        log.error('TODO HOW TO HANDLE?')


def _stream_output(args, data):
    return _update_run(args, data, retry=2)


def _cmd_output(cmd):
    '''Simple non-blocking way to stream the output of a command'''
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    fds = [p.stdout, p.stderr]

    for fd in fds:  # Ensure pipes are set to non-block
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    while len(fds) > 0:
        for fd in select.select(fds, [], [])[0]:
            buff = fd.read(1024)
            if buff == b'':
                fds.remove(fd)
                break
            yield buff
    p.wait()
    if p.returncode != 0:
        raise Exception('Error running command: rc=%d' % p.returncode)


def _run_cmd(args, *cmd):
    _update_status(args, 'RUNNING', 'running: %s' % ' '.join(cmd))
    with open('console.log', 'wb') as f:
        last_update = 0
        last_buff = b''
        for buff in _cmd_output(cmd):
            f.write(buff)
            now = time.time()
            # stream data every 20s or if we have a 1M of data
            if now - last_update > 20 or len(buff) > 1048576:
                if not _stream_output(args, last_buff + buff):
                    last_buff += buff
                else:
                    last_buff = b''
            else:
                last_buff += buff
        if last_buff:
            f.write(buff)
            if not _stream_output(args, last_buff):
                log.warn('Unable to stream part of output: %s', last_buff)


def main(args):
    log.debug('running main with: %r', args)
    _update_status(args, 'RUNNING', 'bya_runner is starting')
    try:
        with open('executable', 'w') as f:
            f.write(sys.stdin.read())
            os.fchmod(f.fileno(), 0o555)
        _run_cmd(args, 'timeout', '10m', 'docker', 'pull', args.container)
        cmd = ['timeout', '%sm' % args.timeout, 'docker', 'run']
        if args.env:
            for env in args.env:
                cmd.append('-e')
                cmd.append(env)
        cmd.extend(
            ['-v', '%s:/bya' % os.getcwd(), args.container, '/bya/executable'])
        _run_cmd(args, *cmd)
        _update_status(args, 'PASSED', 'bya_runner completed')
    except:
        stack = traceback.format_exc()
        log.error(stack)
        _update_status(args, 'FAILED', 'bya_runner failed with: %s' % stack)
    finally:
        if not args.keep_dir:
            shutil.rmtree(RUNNER_DIR)


def get_args(args=None):
    parser = argparse.ArgumentParser('Runner for a BYA job')
    parser.add_argument('--log_level', default='INFO',
                        help='default = %(default)s')
    parser.add_argument('--api_key', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--build_name', required=True)
    parser.add_argument('--build_num', required=True)
    parser.add_argument('--timeout', required=True)
    parser.add_argument('--container', required=True)
    parser.add_argument('--keep-dir', action='store_true', required=False)
    parser.add_argument('--env', action='append')
    args = parser.parse_args(args)
    log.setLevel(args.log_level)
    args.bya_server = _get_params().get('BYA_SERVER')
    log.info('BYA_SERVER set to: %s', args.bya_server)
    return args


if __name__ == '__main__':
    main(get_args())
