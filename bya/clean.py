import time

from bya import settings
from bya.models import jobs

log = settings.get_logger()


def _keep_by_build(b, data):
    if data[0] > 0:
        data[0] -= 1
        return False
    return True


def _keep_by_days(b, data):
    return b.completion_time < data


def clean_builds():
    for job_def in jobs:
        log.debug('scanning %r', job_def)
        unit = job_def.retention.get('unit')
        if unit:
            value = job_def.retention['value']
            log.debug('retention unit(%s) value(%s)', unit, value)

            if unit == 'builds':
                filter_func = _keep_by_build
                filter_data = [value]
            else:
                filter_func = _keep_by_days
                filter_data = time.time() - (24 * 60 * 60 * value)

            # we don't want to delete the most recent or it will screw up
            # our model's logic for numbering the next build
            last_build = True
            for b in job_def.list_builds():
                log.debug('build: %r, data: %r', b, filter_data)
                if not last_build and b.completion_time != 0:
                    if filter_func(b, filter_data):
                        log.info('deleting build: %r - %r', job_def, b)
                        b.delete()
                last_build = False
