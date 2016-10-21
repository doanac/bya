import os
import tempfile
import shutil
import time
import unittest

import yaml

from bya import settings
from bya.models import Build, JobDefinition, JobGroup, Run


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

        settings.JOBS_DIR = os.path.join(self.tempdir, 'jobs')
        os.mkdir(settings.JOBS_DIR)
        settings.BUILDS_DIR = os.path.join(self.tempdir, 'builds')
        os.mkdir(settings.BUILDS_DIR)
        settings.QUEUE_DIR = os.path.join(self.tempdir, 'run-queue')
        os.mkdir(settings.QUEUE_DIR)

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
        self.assertIn('foo=bar', r.params)
        self.assertIn('bam=BAM', r.params)

        r.append_log('hello world\n')
        r.append_log('hello world')
        with r.log_fd() as f:
            self.assertIn('hello world\nhello world', f.read())

    def test_status(self):
        params = {'foo': 'bar', 'bam': 'BAM'}
        r = Run.create(self.tempdir, 'run_foo', 'container_foo', '', params)
        r.set_status('PASSED')
        self.assertEqual(r.PASSED, r.status)
        with self.assertRaises(ValueError):
            r.set_status('BAD')

    # TODO test this run-queue idea


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
            self.assertEqual([], JobDefinition.validate(f))

    def test_description(self):
        """Ensure description is required."""
        del self.jobdef['description']
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(
                ['Missing required attribute: "description".'], errors)

    def test_script(self):
        """Ensure script is required."""
        del self.jobdef['script']
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(['Missing required attribute: "script".'], errors)

    def test_timeout(self):
        """Ensure timeout is required and integer"""
        del self.jobdef['timeout']
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(
                ['Missing required attribute: "timeout".'], errors)

        self.jobdef['timeout'] = '5'
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(['Invalid value for "timeout".'], errors)

    def test_containers(self):
        """Ensure containers are specified"""
        del self.jobdef['containers']
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(
                ['Missing required attribute: "containers".'], errors)

        self.jobdef['containers'] = [{'missing_image_attr': 'blah'}]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(
                ['Container ({\'missing_image_attr\': \'blah\'}) must include '
                 'an "image" attribute'], errors)

    def test_params(self):
        """Ensure params are validated"""
        self.jobdef['params'] = [{'name': 'foo'}]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(0, len(errors))

        self.jobdef['params'] = [{'lbah': 'foo'}]
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(1, len(errors))
            self.assertEqual(
                'Param ({\'lbah\': \'foo\'}) must include a "name" attribute',
                errors[0])

    def test_create_build_noruns(self):
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(0, len(errors))
        job = self._load_job('name')
        with self.assertRaisesRegex(ValueError, 'runs must be a non-empty'):
            job.create_build([])

    def test_create_build_badcontainer(self):
        p = self._write_job('name', self.jobdef)
        with open(p) as f:
            errors = JobDefinition.validate(f)
            self.assertEqual(0, len(errors))
        job = self._load_job('name')

        with self.assertRaisesRegex(ValueError, 'missing attribute "name"'):
            job.create_build([{}])
        with self.assertRaisesRegex(ValueError, 'ssing attribute "container"'):
            job.create_build([{'name': 'foo'}])
        with self.assertRaisesRegex(ValueError, 'Container\(blah\) invalid'):
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
            errors = JobDefinition.validate(f)
            self.assertEqual(0, len(errors))
        job = self._load_job('name')

        with self.assertRaisesRegex(ValueError, 'required parameter: p3'):
            p = {'p1': '1'}  # missing p3
            job.create_build(
                [{'name': 'foo', 'container': 'ubuntu', 'params': p}])

        with self.assertRaisesRegex(ValueError, 'Invalid value for p1.'):
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
        r.set_status('RUNNING')
        self.assertEqual('RUNNING', r.status)
