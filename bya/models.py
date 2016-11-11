import datetime
import functools
import os

from operator import attrgetter

import yaml

from bya import settings

log = settings.get_logger()


class ModelError(Exception):
    def __init__(self, msg, code=500):
        super(ModelError, self).__init__(msg)
        self.status_code = code


class RunQueue(object):
    @staticmethod
    def push(run, host_tag):
        qname = '%s#%f' % (host_tag, datetime.datetime.now().timestamp())
        qlen = len(os.listdir(settings.QUEUE_DIR))
        os.symlink(run.run_dir, os.path.join(settings.QUEUE_DIR, qname))
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
            run = Run(os.path.basename(run), run)
            run.append_log('# Dequeued to: %s\n' % host)
            return run


class Run(object):
    QUEUED = 'QUEUED'
    UNKNOWN = 'UNKNOWN'
    RUNNING = 'RUNNING'
    PASSED = 'PASSED'
    FAILED = 'FAILED'

    @classmethod
    def create(cls, build_dir, name, container, host_tag, params):
        path = os.path.join(build_dir, 'runs')
        if not os.path.exists(path):
            os.mkdir(path)
        path = os.path.join(path, name)
        os.mkdir(path)
        if not host_tag:
            host_tag = '*'
        with open(os.path.join(path, 'container'), 'w') as f:
            f.write(container)
        with open(os.path.join(path, 'host_tag'), 'w') as f:
            f.write(host_tag)
        with open(os.path.join(path, 'params'), 'w') as f:
            for k, v in params.items():
                f.write('%s=%s\n' % (k, v))

        r = cls(name, path)
        RunQueue.push(r, host_tag)
        return r

    def __init__(self, name, run_dir):
        self.name = name
        self.run_dir = run_dir

    def __repr__(self):
        return 'Run(%s)' % (self.name)

    def set_status(self, status):
        if status not in (Run.QUEUED, Run.RUNNING, Run.PASSED, Run.FAILED):
            raise ValueError('Invalid run status: %s' % status)
        with open(os.path.join(self.run_dir, 'status'), 'w') as f:
            f.write(status)

    @property
    def status(self):
        try:
            with open(os.path.join(self.run_dir, 'status')) as f:
                return f.read().strip()
        except FileNotFoundError:
            return self.QUEUED
        except:
            log.exception('unable to read job state')
            return self.UNKNOWN

    @property
    def host_tag(self):
        with open(os.path.join(self.run_dir, 'host_tag')) as f:
            return f.read().strip()

    @property
    def container(self):
        with open(os.path.join(self.run_dir, 'container')) as f:
            return f.read().strip()

    @property
    def params(self):
        with open(os.path.join(self.run_dir, 'params')) as f:
            return f.read().strip()

    def append_log(self, msg):
        with self.log_fd('a') as f:
            f.write(msg)

    def log_fd(self, mode='r'):
        return open(os.path.join(self.run_dir, 'console.log'), mode)


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
                yield(Run(entry.name, entry.path))

    def __repr__(self):
        return 'Build(%d)' % self.number


def _validate_containers_field(val):
    if not val:
        return True
    if type(val) != list:
        return '"containers" attribute must be a list'
    for v in val:
        if type(v) != dict:
            return 'Container value(%s) must of type dict' % v
        elif not v.get('image'):
            return 'Container (%s) must include an "image" attribute' % v
    return True


def _validate_params_field(val):
    if not val:
        return True
    if type(val) != list:
        return '"params" attribute must be a list'
    for v in val:
        if type(v) != dict:
            return 'Param value(%s) must of type dict' % v
        elif not v.get('name'):
            return 'Param (%s) must include a "name" attribute' % v
    return True


class JobDefinition(object):
    """Represents the definition of job that's managed by YAML files under
       settings.JOBS_DIR like:
         job1.yml
         job2.yml
         group/
               job1.yml
               job2.yml
    """
    FIELDS = (
        ('description', lambda x: type(x) == str, True),
        ('timeout', lambda x: type(x) == int, True),
        ('script', lambda x: type(x) == str, True),
        ('containers', _validate_containers_field, True),
        ('params', _validate_params_field, False),
    )

    @classmethod
    def validate(clazz, stream):
        data = yaml.load(stream)
        errors = []
        for attr, validator, required in clazz.FIELDS:
            val = data.get(attr)
            if not val and required:
                errors.append('Missing required attribute: "%s".' % attr)
            elif val:
                r = validator(val)
                if type(r) == str:
                    errors.append(r)
                elif not r:
                    errors.append('Invalid value for "%s".' % attr)
        return errors

    @staticmethod
    def _prop(prop, self):
        if isinstance(self._data, str):
            # lazy load the definition
            with open(self._data) as f:
                self._data = yaml.load(f)
        return self._data.get(prop)

    @classmethod
    def _class_init(clazz):
        # a clever way to give us lazy-loadable object properies
        flag = clazz.__name__ + '_fields_set'
        if getattr(clazz, flag, None):
            return
        attrs = ('description', 'script', 'timeout', 'containers',
                 'params')
        for a in attrs:
            setattr(clazz, a, property(functools.partial(clazz._prop, a)))
        setattr(clazz, flag, True)

    def __init__(self, jobgroup, name, jobfile):
        if '#' in name:
            raise ValueError(
                'Illegal job name(%s). Must not contain #' % name)
        self._class_init()
        self.name = name
        self._data = jobfile
        self.jobgroup = jobgroup

    def _get_builds_dir(self):
        # maintain a flat listing of all builds so that nested stuff like
        #  group/job1.yml
        #  group.yml
        # don't wind sharing directory space
        name = self.name
        if self.jobgroup:
            name = self.jobgroup.name.replace('/', '#')
            if name:
                name += '#'
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
            raise ValueError('\n'.join(errors))

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
