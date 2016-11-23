#!/usr/bin/python3

import argparse
import logging
import sys

logging.basicConfig()
log = logging.getLogger('bya-runner')


def main(args):
    log.debug('running main with: %r', args)
    args.script = sys.stdin.read()
    log.debug('script is: %s', args.script)


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
    args = parser.parse_args(args)
    log.setLevel(args.log_level)
    return args


if __name__ == '__main__':
    main(get_args())
