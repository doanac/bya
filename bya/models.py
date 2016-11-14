import datetime
import os

from operator import attrgetter

import yaml

from bya import settings
from bya.lazy import (
    ModelError,
    Property,
    PropsDir,
    PropsFile,
    StrChoiceProperty,
)

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
        if os.path.exists(settings.QUEUE_DIR):
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
                os.unlink(oldest[0].path)
            except FileNotFoundError:
                log.error('Unexpected race condition handling: %s', run.path)
                return
            run = Run(run)
            run.append_log('# Dequeued to: %s\n' % host)
            return run


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
        StrChoiceProperty('status',
                          (UNKNOWN, QUEUED, RUNNING, PASSED, FAILED), QUEUED),
    )

    @classmethod
    def create(cls, build_dir, name, container, host_tag, params):
        path = os.path.join(build_dir, 'runs')
        if not os.path.exists(path):
            os.mkdir(path)
        path = os.path.join(path, name)
        os.mkdir(path)
        if not host_tag:
            host_tag = '*'

        data = {'container': container, 'host_tag': host_tag, 'params': params}
        PropsDir.create(path, data)
        r = cls(path)
        RunQueue.push(r, host_tag)
        return r

    def append_log(self, msg):
        with self.log_fd('a') as f:
            f.write(msg)

    def log_fd(self, mode='r'):
        return self.open_file('console.log', mode)

    def get_rundef(self):
        builds = os.path.abspath(os.path.join(self.path, '../..'))
        jobname = os.path.basename(os.path.dirname(builds))
        jobdef = jobs.find_jobdef(jobname.replace('#', '/'))

        steps = {
            'container': self.container,
            'params': self.params,
            'timeout': jobdef.timeout,
            'script': jobdef.script,
        }
        return steps


class Build(object):
    QUEUED = 'QUEUED'
    UNKNOWN = 'UNKNOWN'

    @classmethod
    def create(cls, job, runs):
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
                for r in runs:
                    ht = job.get_host_tag(r['container'])
                    Run.create(b.build_dir, r['name'], r['container'], ht,
                               r.get('params'))
                return b
            except FileExistsError:
                pass
        # doubt this could ever happen
        raise RuntimeError('Unable to find next build number for %s' % job)

    def __init__(self, number, build_dir):
        self.number = int(number)
        self.build_dir = build_dir

    def append_to_summary(self, msg):
        with self.summary_fd('w') as f:
            f.write('%s UTC: %s\n' % (datetime.datetime.utcnow(), msg))

    def summary_fd(self, mode='r'):
        return open(os.path.join(self.build_dir, 'summary.log'), mode)

    @property
    def status(self):
        try:
            with open(os.path.join(self.build_dir, 'status')) as f:
                return f.read().strip()
        except FileNotFoundError:
            return self.QUEUED
        except:
            log.exception('unable to read job state')
            return self.UNKNOWN

    @property
    def started(self):
        return os.stat(self.build_dir).st_ctime

    def list_runs(self):
        for entry in os.scandir(os.path.join(self.build_dir, 'runs')):
            if entry.is_dir():
                yield(Run(entry.path))

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
        ContainersProp(),
        ParamsProp(),
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

    def get_last_build(self):
        for b in self.list_builds():
            return b

    def list_builds(self):
        path = self._get_builds_dir()
        if os.path.exists(path):
            listing = os.scandir(path)
            for entry in sorted(listing, key=attrgetter('name'), reverse=True):
                if entry.is_dir():
                    yield(Build(entry.name, entry.path))

    def get_host_tag(self, container):
        for c in self.containers:
            if c['image'] == container:
                return c.get('host_tag')
        raise ValueError('Unknown container: %s' % container)

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

    def create_build(self, runs):
        self._validate_runs(runs)
        return Build.create(self, runs)


class JobGroup(object):
    def __init__(self, parents=None):
        if parents is None:
            parents = []
        self._parents = parents
        self._groups = None
        self._jobs = None

    @property
    def name(self):
        return '/'.join(self._parents)

    def _list(self):
        if self._jobs is not None:  # already loaded
            return
        self._groups = []
        self._jobs = []
        path = os.path.join(settings.JOBS_DIR, '/'.join(self._parents))
        for entry in os.scandir(path):
            if entry.is_file() and entry.name.endswith('.yml'):
                self._jobs.append(
                    JobDefinition(self, entry.name[:-4], entry.path))
            elif entry.is_dir():
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
    PROPS = (
        Property('distro', str),
        Property('mem_total', int),
        Property('cpu_total', int),
        Property('cpu_type', str),
        Property('enlisted', bool, False, False),
        Property('api_key', str)
    )

    @staticmethod
    def list():
        for entry in os.scandir(settings.HOSTS_DIR):
            if entry.is_dir():
                yield Host(entry.path)

    @staticmethod
    def get(name):
        path = os.path.join(settings.HOSTS_DIR, name)
        if not os.path.exists(path):
            raise ModelError('Host(%s) does not exist' % name, 404)
        return Host(path)

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
