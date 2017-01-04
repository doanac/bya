import logging
import os

_here = os.path.realpath(os.path.dirname(__file__))

WORKER_SCRIPT = os.path.join(_here, '../bya_worker.py')
RUNNER_SCRIPT = os.path.join(_here, '../bya_runner.py')

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))
if DEBUG:
    SECRET_KEY = 'UNSAFE FOR PRODUCTION'
else:
    try:
        with open(os.path.join(_here, '../../flask_secret')) as f:
            SECRET_KEY = f.read()
    except:
        SECRET_KEY = os.urandom(24)
        with open(os.path.join(_here, '../../flask_secret'), 'wb') as f:
            f.write(SECRET_KEY)

# used by notifications.py
SERVER_NAME = 'localhost'
EMAIL_NOTIFY_FROM = 'bya@%s' % SERVER_NAME

AUTO_ENLIST_HOSTS = False

TRIGGER_INTERVAL = 120  # 120s / every 2 minutes

LOCAL_SETTINGS = os.path.join(_here, '../../local_settings.py')
_settings_files = (
    '/etc/bya.conf.py',
    LOCAL_SETTINGS,
)
for fname in _settings_files:
    if os.path.exists(fname):
        with open(fname) as f:
            exec(f.read())

JOBS_DIR = os.path.join(_here, '../../job-defs')
BUILDS_DIR = os.path.join(_here, '../../builds')
QUEUE_DIR = os.path.join(_here, '../../run-queue')
RUNNING_DIR = os.path.join(_here, '../../active-runs')
HOSTS_DIR = os.path.join(_here, '../../hosts')
TRIGGERS_DIR = os.path.join(_here, '../../triggers')

SECRETS_FILE = os.path.join(_here, '../../secrets.yml')


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
