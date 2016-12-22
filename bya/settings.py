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
TRIGGERS_DIR = os.path.join(_here, '../../triggers')

SECRETS_FILE = os.path.join(_here, '../../secrets.yml')

TRIGGER_INTERVAL = 120  # 120s / every 2 minutes

logging.bya_initialized = False


def _init_logging():
    if DEBUG:
        level = 'DEBUG'
    else:
        level = 'INFO'
    logging.basicConfig(level=level)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.bya_initialized = True


def get_logger():
    if not logging.bya_initialized:
        _init_logging()
    return logging
