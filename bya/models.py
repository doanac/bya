import datetime
import json
import os
import random
import shutil
import string
import tempfile

import yaml

from bya import settings
from bya.lazy import (
    ModelError,
    Property,
    PropsDir,
    PropsFile,
    StrChoiceProperty,
)
from bya.notifications import NotifyProp
from bya.triggers import TriggerProp

log = settings.get_logger()


class RunQueue(object):
    @staticmethod
    def push(run, host_tag):
        qname = '%s#%f' % (host_tag, datetime.datetime.now().timestamp())
        qlen = len(os.listdir(settings.QUEUE_DIR))
        os.symlink(run.path, os.path.join(settings.QUEUE_DIR, qname))
        run.append_log('# Queued as: %s. %d Runs waiting in front\n' % (
                       qname, qlen))

    @staticmethod
    def take(host, host_tags):
        '''Find the first queued run that matches one of the host tags'''
        oldest = None
        for e in os.scandir(settings.QUEUE_DIR):
            tag, ts = e.name.split('#', 1)
            ts = float(ts)
            if tag == '*' or tag in host_tags:
                if not oldest or ts < oldest[1]:
                    oldest = (e, ts)
        if oldest:
            try:
                run = os.path.join(
                    settings.QUEUE_DIR, os.readlink(oldest[0].path))
                dst = os.path.join(settings.RUNNING_DIR, oldest[0].name)
                os.rename(oldest[0].path, dst)
            except FileNotFoundError:
                log.error('Unexpected race condition handling: %s', run)
                return
            run = Run(run)
            run.append_log('# Dequeued to: %s\n' % host)
            run.get_build().append_to_summary(
                'Dequeued %s to: %s' % (run, host))
            return run

    @staticmethod
    def complete(run, status):
        '''Remove a run's symlink from the RUNNING_DIR'''
        run.get_build().append_to_summary('%s status=%s' % (run, status))
        for e in os.scandir(settings.RUNNING_DIR):
            path = os.readlink(e.path)
            if path == run.path:
                os.unlink(e.path)
                break

    @staticmethod
    def list_running():
        for e in os.scandir(settings.RUNNING_DIR):
            yield Run(os.path.join(settings.QUEUE_DIR, os.readlink(e.path)))

    @staticmethod
    def list_queued():
        for e in os.scandir(settings.QUEUE_DIR):
            yield Run(os.path.join(settings.QUEUE_DIR, os.readlink(e.path)))


class Run(PropsDir):
    QUEUED = 'QUEUED'
    UNKNOWN = 'UNKNOWN'
    RUNNING = 'RUNNING'
    PASSED = 'PASSED'
    FAILED = 'FAILED'

    PROPS = (
        Property('container', str),
        Property('host_tag', str),
        Property('params', dict, required=False),
        Property('api_key', str),
        StrChoiceProperty('status',
                          (UNKNOWN, QUEUED, RUNNING, PASSED, FAILED), QUEUED),
    )

    @classmethod
    def get(clazz, build_name, build_num, run):
        path = os.path.join(settings.BUILDS_DIR, build_name,
                            str(build_num), 'runs', run)
        return clazz(path)

    def update(self, **kwargs):
        super(Run, self).update(**kwargs)
        status = kwargs.get('status')
        if status in (Run.FAILED, Run.PASSED):
            RunQueue.complete(self, status)
            # force build into updating status if all runs have completed
            self.get_build().status

    def append_log(self, msg):
        with self.log_fd('a') as f:
            f.write(msg)

    def log_fd(self, mode='r'):
        return self.open_file('console.log', mode)

    def get_build(self):
        bdir = os.path.abspath(os.path.join(self.path, '../..'))
        bnum = os.path.basename(os.path.dirname(os.path.dirname(self.path)))
        return Build(bnum, bdir)

    def _get_params(self):
        params = {}
        if self.params:
            for k, v in self.params.items():
                params[k] = v
        for k, v in self.get_build().trigger_data.items():
            params[k] = v
        return params

    def get_rundef(self):
        builds = os.path.abspath(os.path.join(self.path, '../..'))
        bname = os.path.basename(os.path.dirname(builds))
        jobdef = jobs.find_jobdef(bname.replace('#', '/'))
        bnum = os.path.basename(os.path.dirname(os.path.dirname(self.path)))

        with open(settings.RUNNER_SCRIPT) as f:
            runner = f.read()

        args = [
            '--api_key', self.api_key,
            '--run', self.name,
            '--build_name', bname,
            '--build_num', bnum,
            '--timeout', str(jobdef.timeout),
            '--container', self.container,
        ]
        for k, v in self._get_params().items():
            args.append('--env')
            args.append('%s=%s' % (k, v))
        return {
            'stdin': jobdef.script,
            'args': args,
            'runner': runner,
            'secrets': jobdef.get_secrets(),
        }


class Build(object):
    QUEUED = 'QUEUED'
    UNKNOWN = 'UNKNOWN'

    @classmethod
    def create(cls, job, runs, trigger_data=None):
        """Creates a new Build with an increased build number"""
        path = job._get_builds_dir()
        if not os.path.exists(path):
            os.mkdir(path)
        b = job.get_last_build()
        if not b:
            b = 0
        else:
            b = b.number
        # try to find the next build number in a concurrently safe way
        # os.mkdir is atomic, so try up to 10 times before complaining
        for b in range(b, b+10):
            b += 1
            try:
                p = os.path.join(path, str(b))
                os.mkdir(os.path.join(path, str(b)))
                b = cls(b, p)
                b.append_to_summary('Build queued')
                b._create_runs(job, runs, trigger_data)
                return b
            except FileExistsError:
                pass
        # doubt this could ever happen
        raise RuntimeError('Unable to find next build number for %s' % job)

    def __init__(self, number, build_dir):
        self.number = int(number)
        self.build_dir = build_dir
        self.name = os.path.basename(os.path.dirname(build_dir))

    def append_to_summary(self, msg):
        with self.summary_fd('a') as f:
            f.write('%s UTC: %s\n' % (datetime.datetime.utcnow(), msg))

    def summary_fd(self, mode='r'):
        return open(os.path.join(self.build_dir, 'summary.log'), mode)

    @property
    def summary(self):
        with self.summary_fd() as f:
            return f.read()

    def _create_runs(self, job, runs, trigger_data):
        with open(os.path.join(self.build_dir, 'trigger_data'), 'w') as f:
            if trigger_data is None:
                trigger_data = {}
            json.dump(trigger_data, f)
        path = os.path.join(self.build_dir, 'runs')
        if not os.path.exists(path):
            os.mkdir(path)
        for r in runs:
            host_tag = job.get_host_tag(r['container'])
            if not host_tag:
                host_tag = '*'
            key = ''.join(
                random.SystemRandom().choice(
                    string.ascii_uppercase + string.digits) for _ in range(16))
            data = {
                'container': r['container'],
                'host_tag': host_tag,
                'params': r.get('params'),
                'api_key': key,
            }
            rp = os.path.join(path, r['name'])
            Run.create(rp, data)
            RunQueue.push(Run(rp), host_tag)

    def _notify(self, status):
        jobdef = jobs.find_jobdef(self.name.replace('#', '/'))
        NotifyProp.notify_build(jobdef, self, status)

    @property
    def completion_time(self):
        status_file = os.path.join(self.build_dir, 'status')
        try:
            return os.stat(status_file).st_mtime
        except FileNotFoundError:
            return 0

    @property
    def status(self):
        status_file = os.path.join(self.build_dir, 'status')
        try:
            with open(status_file) as f:
                return f.read().strip()
        except FileNotFoundError:
            # look at all the runs and figure out a status
            states = set([x.status for x in self.list_runs()])
            if Run.RUNNING in states:
                if Run.FAILED in states:
                    return 'Running with Failure(s)'
                return Run.RUNNING
            if not states - set([Run.PASSED, Run.FAILED]):
                status = 'Completed'
                if Run.FAILED in states:
                    status = 'Completed with Failure(s)'
                # save state for easier future lookups
                with open(status_file, 'w') as f:
                    f.write(status)
                self._notify(status)
                return status
            return self.QUEUED
        except:
            log.exception('unable to read job state')
            return self.UNKNOWN

    @property
    def started(self):
        return os.stat(self.build_dir).st_ctime

    @property
    def started_utc(self):
        return datetime.datetime.fromtimestamp(self.started)

    @property
    def trigger_data(self):
        try:
            with open(os.path.join(self.build_dir, 'trigger_data')) as f:
                return json.load(f)
        except:
            log.exception('error loading trigger data')
            return {}

    def list_runs(self):
        return Run.list(os.path.join(self.build_dir, 'runs'))

    def get_run(self, name):
        return Run.get(self.name, self.number, name)

    def delete(self):
        tmpdir = tempfile.mkdtemp(dir=settings.DATA_DIR)
        dst = os.path.join(tmpdir, 'build')
        os.rename(self.build_dir, dst)
        shutil.rmtree(tmpdir)

    def __repr__(self):
        return 'Build(%d)' % self.number


class ContainersProp(Property):
    def __init__(self):
        super(ContainersProp, self).__init__('containers', list)

    def validate(self, value):
        value = super(ContainersProp, self).validate(value)
        for v in value:
            if type(v) != dict:
                raise ModelError(
                    'Container value(%s) must of type dict' % v, 400)
            elif not v.get('image'):
                raise ModelError(
                    'Container(%s) must include an "image" attribute' % v, 400)


class ParamsProp(Property):
    def __init__(self):
        empty = []
        super(ParamsProp, self).__init__('params', list, empty, False)

    def validate(self, value):
        value = super(ParamsProp, self).validate(value)
        for v in value:
            if type(v) != dict:
                raise ModelError('Param value(%s) must of type dict' % v, 400)
            elif not v.get('name'):
                raise ModelError(
                    'Param(%s) must include a "name" attribute' % v, 400)


class RetentionProp(Property):
    def __init__(self):
        empty = {}
        super(RetentionProp, self).__init__('retention', dict, empty, False)

    def validate(self, value):
        value = super(RetentionProp, self).validate(value)
        if value:
            unit = value.get('unit')
            if unit not in ('days', 'builds'):
                raise ModelError(
                    'Invalid retention unit(%s). Must be "days" or "builds"' %
                    unit)
            v = value.get('value')
            if not v or type(v) != int:
                raise ModelError(
                    'Invalid retention value(%s). Must be an integer' % v)


class JobDefinition(PropsFile):
    """Represents the definition of job that's managed by YAML files under
       settings.JOBS_DIR like:
         job1.yml
         job2.yml
         group/
               job1.yml
               job2.yml
    """
    PROPS = (
        Property('description', str),
        Property('timeout', int),
        Property('script', str),
        Property('secrets', list, required=False),
        RetentionProp(),
        ContainersProp(),
        ParamsProp(),
        TriggerProp(),
        NotifyProp(),
    )

    def __init__(self, jobgroup, name, jobfile):
        if '#' in name:
            raise ValueError(
                'Illegal job name(%s). Must not contain #' % name)
        super(JobDefinition, self).__init__(name, jobfile, yaml.load)
        self.jobgroup = jobgroup

    def _get_builds_dir(self):
        # maintain a flat listing of all builds so that nested stuff like
        #  group/job1.yml
        #  group.yml
        # don't wind sharing directory space
        name = self.name
        if self.jobgroup:
            n = self.jobgroup.name.replace('/', '#')
            if n:
                name = n + '#' + name
        return os.path.join(settings.BUILDS_DIR, name)

    def get_trigger_cache(self):
        return os.path.join(self._get_builds_dir(), 'triggers.cache')

    def get_last_build(self):
        for b in self.list_builds():
            return b

    def get_build(self, build_num):
        path = os.path.join(self._get_builds_dir(), str(build_num))
        if not os.path.isdir(path):
            raise ModelError(
                'Build #%d does not exist' % build_num, 404)
        return Build(build_num, path)

    def list_builds(self):
        def keyfunction(x):
            try:
                v = int(x.name)
                return '%08d' % v
            except:
                return x.name

        path = self._get_builds_dir()
        if os.path.exists(path):
            listing = os.scandir(path)
            for entry in sorted(listing, key=keyfunction, reverse=True):
                if entry.is_dir():
                    yield(Build(entry.name, entry.path))

    def get_host_tag(self, container):
        for c in self.containers:
            if c['image'] == container:
                return c.get('host_tag')
        raise ValueError('Unknown container: %s' % container)

    def get_secrets(self):
        secrets = {}
        if self.secrets and os.path.exists(settings.SECRETS_FILE):
            with open(settings.SECRETS_FILE) as f:
                secret_vals = yaml.load(f)
            for s in self.secrets:
                secrets[s] = secret_vals.get(s, '')
        return secrets

    def can_rebuild(self, user):
        # TODO enforce job-level permissions
        return user.is_authenticated

    def __repr__(self):
        return 'Job(%s)' % self.name

    def _validate_params(self, errors, params):
        required_params = self.params
        if not required_params:
            required_params = {}
        required_dict = {x['name']: x for x in required_params}
        required_names = set(required_dict.keys())
        names = set(params.keys())

        for missing in required_names - names:
            if 'defval' in required_dict[missing]:
                params[missing] = required_dict[missing]['defval']
            else:
                errors.append('Missing required parameter: %s' % missing)
        for unknown in names - required_names:
            errors.append('Unknown parameter: %s' % unknown)

        for name, val in params.items():
            choices = required_dict[name].get('choices')
            if choices:
                if val not in choices:
                    errors.append(
                        'Invalid value for %s. Must be one of: %s' % (
                            name, choices))
        return params

    def _validate_run(self, run):
        errors = []
        if 'name' not in run:
            errors.append('Run(%s) missing attribute "name"' % run)
        container = run.get('container')
        if not container:
            errors.append('Run(%s) missing attribute "container"' % run)
        else:
            valid_containers = [x['image'] for x in self.containers]
            if container not in valid_containers:
                errors.append('Container(%s) invalid. Must be one of: %s' % (
                              container, valid_containers))
        run['params'] = self._validate_params(errors, run.get('params', {}))
        return errors

    def _validate_runs(self, runs):
        errors = []
        if runs and len(runs) > 0:
            for run in runs:
                errors.extend(self._validate_run(run))
        else:
            errors.append('runs must be a non-empty list')
        if errors:
            raise ModelError('\n'.join(errors), 400)

    def create_build(self, runs, trigger_data=None):
        self._validate_runs(runs)
        return Build.create(self, runs, trigger_data)

    def rebuild(self, build, user='unknown'):
        runs = []
        for run in build.list_runs():
            runs.append({
                'name': run.name,
                'params': run.params or {},
                'container': run.container,
            })
        b = self.create_build(runs, build.trigger_data)
        b.append_to_summary(
            '"%s" triggered rebuild of: %d' % (user, build.number))
        return b


class JobGroup(object):
    def __init__(self, parents=None):
        if parents is None:
            parents = []
        self._parents = parents
        self._groups = None
        self._jobs = None

    def __iter__(self):
        for x in self.get_jobdefs():
            yield x
        for group in self.get_groups():
            for x in group:
                yield x

    @property
    def name(self):
        return '/'.join(self._parents)

    def _list(self):
        # TODO this logic isn't working under gunicorn
        # need a better API for accessing jobs and groups
        if self._jobs is not None:  # already loaded
            return
        self._groups = []
        self._jobs = []
        path = os.path.join(settings.JOBS_DIR, '/'.join(self._parents))
        for entry in os.scandir(path):
            if entry.is_file() and entry.name.endswith('.yml'):
                self._jobs.append(
                    JobDefinition(self, entry.name[:-4], entry.path))
            elif entry.is_dir() and entry.name != '.git':
                self._groups.append(JobGroup(self._parents + [entry.name]))

    def get_groups(self):
        self._list()
        return self._groups

    def find_jobgroup(self, path):
        assert path[0] != '/'
        real_path = os.path.join(settings.JOBS_DIR, path)
        if not os.path.isdir(real_path):
            raise ModelError('JobGroup(%s) not found' % path, 404)
        return JobGroup(path.split('/'))

    def get_jobdefs(self):
        self._list()
        return self._jobs

    def find_jobdef(self, path):
        path, name = os.path.split(path)
        name = name + '.yml'
        if path:
            g = self.find_jobgroup(path)
        else:
            g = self
        for entry in os.scandir(os.path.join(settings.JOBS_DIR, g.name)):
            if entry.is_file() and entry.name == name:
                return JobDefinition(g, entry.name[:-4], entry.path)
        raise ModelError('JobDefinition(%s) not found' % path, 404)

jobs = JobGroup()


class Host(PropsDir):
    PROPS_DIR = settings.HOSTS_DIR
    PROPS = (
        Property('distro', str),
        Property('mem_total', int),
        Property('cpu_total', int),
        Property('cpu_type', str),
        Property('enlisted', bool, False, False),
        Property('api_key', str),
        Property('concurrent_runs', int),
        Property('host_tags', str),
    )

    def ping(self):
        # TODO limit file size to 1M (>30 days)
        with self.open_file('pings.log', mode='a') as f:
            f.write('%d\n' % datetime.datetime.now().timestamp())

    @property
    def online(self):
        """Online means we've been "pinged" in the last 3 minutes."""
        try:
            with self.open_file('pings.log') as f:
                mtime = os.fstat(f.fileno()).st_mtime
                now = datetime.datetime.now().timestamp()
                return now - mtime < 180  # pinged in last 3 minutes
        except FileNotFoundError:
            return False
