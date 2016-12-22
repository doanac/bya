import importlib.util
import os
import shutil
import unittest

from unittest.mock import patch

from tests import ModelTest

from bya.models import jobs, Run, RunQueue
from bya.views import app


class RunnerTests(ModelTest):

    def setUp(self):
        super(RunnerTests, self).setUp()
        app.config['TESTING'] = True
        self.app = app.test_client()

        self.runner_dir = os.path.join(self.tempdir, 'runner')
        os.mkdir(self.runner_dir)

        src = os.path.join(os.path.dirname(__file__), '../bya_runner.py')
        dst = os.path.join(self.runner_dir, 'bya_runner.py')
        shutil.copy(src, dst)

        spec = importlib.util.spec_from_file_location('bya_runner', dst)
        self.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runner)
        self.runner._post = self._post
        self._create_run()

    def _post(self, url, data, headers, retry=1):
        resp = self.app.post(
            url, data=data, headers=headers, content_type='application/json')
        return resp.status_code == 200

    def _create_run(self):
        jobname = 'jobname_foo'
        self._write_job(jobname, self.jobdef)
        j = jobs.find_jobdef(jobname)
        j.create_build([{'name': 'foo', 'container': 'busybox'}])
        self.run = RunQueue.take('host1', ['tag'])
        self.rundef = self.run.get_rundef()
        self.args = ['--keep-dir']
        for arg in self.rundef['args']:
            self.args.append(arg)

    def _exec(self, args, script):
        args = self.runner.get_args(args)
        with patch('sys.stdin') as stdin:
            stdin.read.return_value = script
            cwd = os.getcwd()
            try:
                os.chdir(self.runner_dir)
                self.runner.main(args)
            finally:
                os.chdir(cwd)

    @unittest.skipIf(not os.path.exists('/usr/bin/docker'),
                     'docker is not installed')
    def test_simple(self):
        self._exec(self.args, "#!/bin/sh\necho hello world\n")
        run = Run(self.run.path)
        self.assertEqual(Run.PASSED, run.status)
