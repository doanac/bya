import os
import tempfile
import shutil
import time
import unittest

import yaml

from bya import settings
from bya.models import (
    Build, Host, JobDefinition, JobGroup, ModelError, Run, RunQueue, jobs
)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        super(TempDirTest, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)


class ModelTest(TempDirTest):
    def setUp(self):
        super(ModelTest, self).setUp()
        self.jobsdir = settings.JOBS_DIR
        self.buildsdir = settings.BUILDS_DIR
        self.queuedir = settings.QUEUE_DIR
        self.hostsdir = settings.HOSTS_DIR

        settings.JOBS_DIR = os.path.join(self.tempdir, 'jobs')
        os.mkdir(settings.JOBS_DIR)
        settings.BUILDS_DIR = os.path.join(self.tempdir, 'builds')
        os.mkdir(settings.BUILDS_DIR)
        settings.QUEUE_DIR = os.path.join(self.tempdir, 'run-queue')
        os.mkdir(settings.QUEUE_DIR)
        settings.HOSTS_DIR = os.path.join(self.tempdir, 'hosts')
        os.mkdir(settings.HOSTS_DIR)

        self.jobdef = {
            'description': 'test_simple',
            'script': 'exit 0',
            'timeout': 5,
            'containers': [{'image': 'ubuntu'}],
        }

    def tearDown(self):
        super(ModelTest, self).tearDown()
        settings.JOBS_DIR = self.jobsdir
        settings.BUILDS_DIR = self.buildsdir
        settings.QUEUE_DIR = self.queuedir
        settings.HOSTS_DIR = self.hostsdir

    @staticmethod
    def _write_job(name, jobdef):
        path = os.path.join(settings.JOBS_DIR, name + '.yml')
        parent = os.path.dirname(path)
        if not os.path.exists(parent):
            os.mkdir(parent)
        with open(path, 'w') as f:
            yaml.dump(jobdef, f)
        return path

    @staticmethod
    def _load_job(name):
        path = os.path.join(settings.JOBS_DIR, name + '.yml')
        return JobDefinition(None, name, path)


class TestRun(ModelTest):
    def test_create(self):
        params = {'foo': 'bar', 'bam': 'BAM'}
        r = Run.create(self.tempdir, 'run_foo', 'container_foo', '', params)

        self.assertEqual('container_foo', r.container)
        self.assertEqual('bar', r.params['foo'])
        self.assertIn('BAM', r.params['bam'])

        r.append_log('hello world\n')
        r.append_log('hello world')
        with r.log_fd() as f:
            self.assertIn('hello world\nhello world', f.read())

    def test_status(self):
        params = {'foo': 'bar', 'bam': 'BAM'}
        r = Run.create(self.tempdir, 'run_foo', 'container_foo', '', params)
        r.update(status='PASSED')
        r = Run(r.path)
        self.assertEqual(r.PASSED, r.status)
        with self.assertRaises(ModelError):
            r.update(status='BAD')

    def test_queue(self):
        params = {'foo': 'bar', 'bam': 'BAM'}
        Run.create(self.tempdir, 'run_foo', 'container_foo', 'tag', params)
        Run.create(self.tempdir, 'run_bar', 'container_foo', 'tag', params)
        Run.create(self.tempdir, 'run_X', 'container_foo', 'tag2', params)

        self.assertIsNone(RunQueue.take('host1', ['nosuchtags']))

        # not the oldest run, but matches the tag
        r = RunQueue.take('host1', ['tag2'])
        self.assertEqual('run_X', r.name)

        r = RunQueue.take('host2', ['tag'])
        self.assertEqual('run_foo', r.name)

        r = RunQueue.take('host1', ['tag'])
        self.assertEqual('run_bar', r.name)
        with r.log_fd() as f:
            self.assertIn('# Dequeued to: host1', f.read())

        # empty queue now
        self.assertIsNone(RunQueue.take('host2', ['tag']))

    def test_full_run(self):
        jobname = 'jobname_foo'
        self._write_job(jobname, self.jobdef)
        j = jobs.find_jobdef(jobname)
        j.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        d = RunQueue.take('host1', ['tag']).get_rundef()
        self.assertEqual(self.jobdef['timeout'], d['timeout'])
        self.assertEqual(self.jobdef['script'], d['script'])


class TestBuild(TempDirTest):
    def test_build(self):
        b = Build(12, self.tempdir)
        b.append_to_summary('hello there')
        with b.summary_fd() as f:
            self.assertIn('hello there', f.read())
        self.assertEqual('QUEUED', b.status)
        self.assertGreater(time.time(), b.started)


class TestValidator(ModelTest):
    def test_simple_pass(self):
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            JobDefinition.validate(yaml.load(f.read()))

    def test_containers(self):
        """Ensure containers are specified"""
        del self.jobdef['containers']
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            msg = 'Missing required attribute: "containers".'
            with self.assertRaisesRegex(ModelError, msg):
                JobDefinition.validate(yaml.load(f.read()))

        self.jobdef['containers'] = [{'missing_image_attr': 'blah'}]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            msg = 'Container\(.*\) must include an "image" attribute'
            with self.assertRaisesRegex(ModelError, msg):
                JobDefinition.validate(yaml.load(f.read()))

    def test_params(self):
        """Ensure params are validated"""
        self.jobdef['params'] = [{'name': 'foo'}]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            JobDefinition.validate(yaml.load(f.read()))

        self.jobdef['params'] = [{'lbah': 'foo'}]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            msg = 'Param\(.*\) must include a "name" attribute'
            with self.assertRaisesRegex(ModelError, msg):
                JobDefinition.validate(yaml.load(f.read()))

    def test_create_build_noruns(self):
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            JobDefinition.validate(yaml.load(f.read()))
        job = self._load_job('name')
        with self.assertRaisesRegex(ModelError, 'runs must be a non-empty'):
            job.create_build([])

    def test_create_build_badcontainer(self):
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            JobDefinition.validate(yaml.load(f.read()))
        job = self._load_job('name')

        with self.assertRaisesRegex(ModelError, 'missing attribute "name"'):
            job.create_build([{}])
        with self.assertRaisesRegex(ModelError, 'ssing attribute "container"'):
            job.create_build([{'name': 'foo'}])
        with self.assertRaisesRegex(ModelError, 'Container\(blah\) invalid'):
            job.create_build([{'name': 'foo', 'container': 'blah'}])
        job.create_build([{'name': 'foo', 'container': 'ubuntu'}])

    def test_create_build_badparams(self):
        self.jobdef['params'] = [
            {'name': 'p1', 'choices': ['1', '2']},
            {'name': 'p2', 'defval': '12'},
            {'name': 'p3'}
        ]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            JobDefinition.validate(yaml.load(f.read()))
        job = self._load_job('name')

        with self.assertRaisesRegex(ModelError, 'required parameter: p3'):
            p = {'p1': '1'}  # missing p3
            job.create_build(
                [{'name': 'foo', 'container': 'ubuntu', 'params': p}])

        with self.assertRaisesRegex(ModelError, 'Invalid value for p1.'):
            p = {'p1': '3', 'p3': 'blah'}  # invalid choice
            job.create_build(
                [{'name': 'foo', 'container': 'ubuntu', 'params': p}])


class TestAll(ModelTest):
    def setUp(self):
        super(TestAll, self).setUp()
        self._write_job('simple', self.jobdef)
        jobs = JobGroup()
        job = jobs.get_jobdefs()[0]
        self.build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])

    def test_list(self):
        self.assertEqual(['foo'], [x.name for x in self.build.list_runs()])

    def test_status(self):
        r = list(self.build.list_runs())[0]
        self.assertEqual('QUEUED', r.status)
        r.update(status='RUNNING')
        r = Run(r.path)
        self.assertEqual('RUNNING', r.status)


class HostTest(ModelTest):
    def setUp(self):
        super(HostTest, self).setUp()
        props = {
            'distro': 'ubuntu',
            'mem_total': 10,
            'cpu_total': 2,
            'cpu_type': 'x86',
            'api_key': '1234',
        }
        Host.create(os.path.join(settings.HOSTS_DIR, 'host1'), props)
        props['cpu_type'] = 'aarch64'
        Host.create(os.path.join(settings.HOSTS_DIR, 'host2'), props)

    def test_list(self):
        hosts = [x.name for x in Host.list()]
        self.assertEqual(2, len(hosts))

    def test_get(self):
        with self.assertRaises(ModelError):
            Host.get('bad name')
        self.assertEqual('aarch64', Host.get('host2').cpu_type)
