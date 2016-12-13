#!/usr/bin/env python3
import argparse
import sys

from bya.models import ModelError, jobs
from bya.views import app


def _run(args):
    app.run(args.host, args.port)


def _validate_jobdef(args):
    try:
        j = jobs.find_jobdef(args.jobdef)
        j.timeout  # force loading of data
        j.validate(j._data)
    except ModelError as e:
        sys.exit(e)


def main():
    parser = argparse.ArgumentParser(
        description='Manage BYA application')

    sub = parser.add_subparsers(title='Commands', metavar='')
    p = sub.add_parser('runserver', help='Run webserver')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('-p', '--port', type=int, default=8000)
    p.set_defaults(func=_run)

    p = sub.add_parser('validate-jobdef', help='Validate a job-defintion')
    p.add_argument('jobdef')
    p.set_defaults(func=_validate_jobdef)

    args = parser.parse_args()
    if getattr(args, 'func', None):
        args.func(args)

if __name__ == '__main__':
    main()
