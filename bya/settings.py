import logging
import os

_here = os.path.realpath(os.path.dirname(__file__))

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))

JOBS_DIR = os.path.join(_here, '../../job-defs')
BUILDS_DIR = os.path.join(_here, '../../builds')
QUEUE_DIR = os.path.join(_here, '../../run-queue')
HOSTS_DIR = os.path.join(_here, '../../hosts')


def get_logger():
    return logging
