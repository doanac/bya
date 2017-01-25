#!/usr/bin/env python3
import argparse
import sys

from bya.clean import clean_builds
from bya.daemon import SmartDaemonRunner
from bya.models import ModelError, jobs
from bya.views import app


def _dev_server(args):
    app.run(args.host, args.port)


def _validate_jobdef(args):
    try:
        j = jobs.find_jobdef(args.jobdef)
        j.timeout  # force loading of data
        j.validate(j._data)
    except ModelError as e:
        sys.exit(e)


def _gunicorn(args):
    cmd = [
        'gunicorn',
        '-w', str(args.workers),
        '-b', '%s:%d' % (args.host, args.port),
        'bya.views:app',
    ]

    class App():
        def __init__(self):
            self.stdin_path = '/dev/null'
            self.stdout_path = args.log
            self.pidfile_path = args.pid
            self.pidfile_timeout = 5

        def run(self):
            from gunicorn.app.wsgiapp import run
            sys.argv = cmd
            sys.exit(run())

    app = App()
    runner = SmartDaemonRunner(app, [sys.argv[0], args.action])
    runner.do_action()


def _triggers(args):
    class App():
        def __init__(self):
            self.stdin_path = '/dev/null'
            self.stdout_path = args.log
            self.pidfile_path = args.pid
            self.pidfile_timeout = 5

        def run(self):
            from bya.triggers import main
            main(None)

    app = App()
    runner = SmartDaemonRunner(app, [sys.argv[0], args.action])
    runner.do_action()


def _clean_builds(args):
    clean_builds()


def main():
    parser = argparse.ArgumentParser(
        description='Manage BYA application')

    sub = parser.add_subparsers(title='Commands', metavar='')
    p = sub.add_parser('devserver', help='Run development webserver')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('-p', '--port', type=int, default=8000)
    p.set_defaults(func=_dev_server)

    p = sub.add_parser('validate-jobdef', help='Validate a job-defintion')
    p.add_argument('jobdef')
    p.set_defaults(func=_validate_jobdef)

    p = sub.add_parser('gunicorn', help='Run gunicorn daemon')
    p.add_argument('--log', default='/tmp/bya-gunicorn.log')
    p.add_argument('--pid', default='/tmp/bya-gunicorn.pid')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('-p', '--port', type=int, default=8000)
    p.add_argument('-w', '--workers', type=int, default=1)
    p.add_argument('action', choices=('start', 'stop', 'restart', 'status'))
    p.set_defaults(func=_gunicorn)

    p = sub.add_parser('triggers', help='Run bya triggers daemon')
    p.add_argument('--log', default='/tmp/bya-triggers.log')
    p.add_argument('--pid', default='/tmp/bya-triggers.pid')
    p.add_argument('action', choices=('start', 'stop', 'restart', 'status'))
    p.set_defaults(func=_triggers)

    p = sub.add_parser('clean-builds', help='Clean up old builds')
    p.set_defaults(func=_clean_builds)

    args = parser.parse_args()
    if getattr(args, 'func', None):
        args.func(args)

if __name__ == '__main__':
    main()
