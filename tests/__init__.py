import os
import tempfile
import shutil
import unittest

import yaml

from bya import settings
from bya.models import Host, JobDefinition


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
        Host.PROPS_DIR = settings.HOSTS_DIR

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
        Host.PROPS_DIR = settings.HOSTS_DIR

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
