import logging
import os

_here = os.path.realpath(os.path.dirname(__file__))

WORKER_SCRIPT = os.path.join(_here, '../bya_worker.py')
RUNNER_SCRIPT = os.path.join(_here, '../bya_runner.py')

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))

AUTO_ENLIST_HOSTS = False

JOBS_DIR = os.path.join(_here, '../../job-defs')
BUILDS_DIR = os.path.join(_here, '../../builds')
QUEUE_DIR = os.path.join(_here, '../../run-queue')
RUNNING_DIR = os.path.join(_here, '../../active-runs')
HOSTS_DIR = os.path.join(_here, '../../hosts')


def get_logger():
    return logging
