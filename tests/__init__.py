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
        self.mocked_dirs = (
            'JOBS_DIR', 'BUILDS_DIR', 'QUEUE_DIR', 'RUNNING_DIR', 'HOSTS_DIR',
            'TRIGGERS_DIR')

        for attr in self.mocked_dirs:
            setattr(self, attr, getattr(settings, attr))
            setattr(settings, attr, os.path.join(self.tempdir, attr))
            os.mkdir(getattr(settings, attr))

        settings.SECRETS_FILE = os.path.join(self.tempdir, 'secrets.yml')
        Host.PROPS_DIR = settings.HOSTS_DIR

        self.jobdef = {
            'description': 'test_simple',
            'script': 'exit 0',
            'timeout': 5,
            'containers': [{'image': 'ubuntu'}, {'image': 'busybox'}],
        }

    def tearDown(self):
        super(ModelTest, self).tearDown()
        for attr in self.mocked_dirs:
            setattr(settings, attr, getattr(self, attr))
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
