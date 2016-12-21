import json
import os

import requests

from bya import settings
from bya.lazy import ModelError, Property

log = settings.get_logger()


class Trigger(object):
    @classmethod
    def validate(clazz, value):
        for x in clazz.ATTRS:
            if not value.get(x):
                raise ModelError(
                    'Missing attribute "%s" in %s' % (x, value), 400)


class GitChecker(object):
    def __init__(self, job_def, trigger):
        self.job_def = job_def
        self.cache = job_def.get_trigger_cache()
        self.refs = trigger['refs']
        self.http_url = trigger['http_url']

    def _get_cur_refs(self):
        try:
            with open(self.cache) as f:
                return json.load(f)
        except:
            return {}

    def _save_refs(self, refs):
        path = os.path.dirname(self.cache)
        if not os.path.isdir(path):
            os.mkdir(path)
        with open(self.cache, 'w') as f:
            json.dump(refs, f)

    def changed(self):
        url = self.http_url
        log.info('git-trigger looking for changes to: %s', url)
        if url[-1] != '/':
            url += '/'
        url += 'info/refs?service=git-upload-pack'
        resp = requests.get(url)
        if resp.status_code != requests.codes.ok:
            log.error('git-trigger to check %s for changes: %d %s',
                      url, resp.status_code, resp.reason)
            return False

        changed = False
        refs = self._get_cur_refs()
        for line in resp.text.splitlines()[2:]:
            if line == '0000':
                break
            log.debug('git-trigger looking at ref: %s', line)
            sha, ref = line.split(' ', 1)
            if ref in self.refs:
                cur = refs.get(ref, '')
                if cur != sha:
                    log.info('git-trigger %s %s change %s->%s',
                             self.http_url, ref, cur, sha)
                    changed = True
                    refs[ref] = sha
        self._save_refs(refs)
        return changed


class GitTrigger(Property):
    def __init__(self):
        super(GitTrigger, self).__init__('git-trigger', dict)

    def validate(self, value):
        v = super(GitTrigger, self).validate(value)
        if type(v) != dict:
            raise ModelError('GitTrigger value(%s) must of type dict' % v, 400)
        if not value.get('http_url'):
            raise ModelError(
                'GitTrigger(%s) must include an "http_url" attribute' % v, 400)
        refs = value.get('refs')
        if not refs or type(refs) != list:
            raise ModelError(
                'GitTrigger(%s) must include a non-empty list "refs"', 400)
        for ref in refs:
            if not ref.startswith('refs/'):
                raise ModelError(
                    'GitTrigger(%s) refs must start with "refs/"', 400)

    def get_checker(self, job_def, trigger):
        return GitChecker(job_def, trigger)

TRIGGERS = {
    'git': GitTrigger(),
}


class TriggerProp(Property):
    def __init__(self):
        super(TriggerProp, self).__init__('triggers', list, required=False)

    def validate(self, value):
        value = super(TriggerProp, self).validate(value)
        for v in value:
            if type(v) != dict:
                raise ModelError(
                    'Trigger value(%s) must of type dict' % v, 400)
            t = v.get('type')
            if not t:
                raise ModelError(
                    'Trigger(%s) must include a "type" attribute' % v, 400)
            trigger = TRIGGERS.get(t)
            if not trigger:
                raise ModelError(
                    'Trigger(%s) does not exist' % t, 400)
            trigger.validate(v)

            runs = v.get('runs')
            if not runs or type(runs) != list:
                raise ModelError(
                    'Trigger(%s) must include a list or "runs"' % v, 400)


class TriggerManager(object):
    def __init__(self, job_defs):
        self.job_defs = job_defs
        self.props_dir = settings.TRIGGERS_DIR

    def run(self):
        log.info('Checking triggers')
        for job_def in self.job_defs:
            if job_def.triggers:
                for trigger in job_def.triggers:
                    t = TRIGGERS[trigger['type']]
                    checker = t.get_checker(job_def, trigger)
                    if checker.changed():
                        b = job_def.create_build(trigger['runs'])
                        b.append_to_summary(
                            'Triggered by %s' % trigger['type'])


def main(job_names):
    import time
    from bya.models import jobs

    job_defs = []
    if not job_names:
        job_defs = list(jobs)
    else:
        for name in job_names:
            job_defs.append(jobs.find_jobdef(name))

    mgr = TriggerManager(job_defs)
    last_run = 0
    while True:
        sleep = settings.TRIGGER_INTERVAL - (time.time() - last_run)
        if sleep > 0:
            log.debug('Waiting %d before running again', sleep)
            time.sleep(sleep)
        last_run = time.time()
        mgr.run()

if __name__ == '__main__':
    main(None)
