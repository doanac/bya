import importlib.util
import json as jsonlib
import os
import shutil

from configparser import ConfigParser

from tests import ModelTest

from bya import settings
from bya.models import Host, jobs
from bya.views import app


class WorkerTests(ModelTest):

    def setUp(self):
        super(WorkerTests, self).setUp()
        app.config['TESTING'] = True
        self.app = app.test_client()

        self.worker_dir = os.path.join(self.tempdir, 'worker')
        os.mkdir(self.worker_dir)

        src = os.path.join(os.path.dirname(__file__), '../bya_worker.py')
        dst = os.path.join(self.worker_dir, 'bya_worker.py')
        shutil.copy(src, dst)

        spec = importlib.util.spec_from_file_location('bya_worker', dst)
        self.worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.worker)
        self.worker_version = str(os.stat(settings.WORKER_SCRIPT).st_mtime)

    def _run_worker(self, args):
        args = self.worker.get_args(args)
        args.server.CRON_FILE = os.path.join(self.worker_dir, 'cron')

        def _get(resource, params, headers):
            resp = self.app.get(resource, query_string=params, headers=headers)
            resp.text = resp.data.decode()

            def as_json():
                return jsonlib.loads(resp.text)
            resp.json = as_json
            return resp

        def _post(resource, json):
            data = jsonlib.dumps(json)
            return self.app.post(
                resource, data=data, content_type='application/json')

        def _patch(resource, json, headers):
            data = jsonlib.dumps(json)
            resp = self.app.patch(resource, data=data, headers=headers,
                                  content_type='application/json')
            resp.text = resp.data.decode()
            return resp

        def _delete(resource, headers):
            return self.app.delete(resource, headers=headers)
        args.server.requests.get = _get
        args.server.requests.post = _post
        args.server.requests.patch = _patch
        args.server.requests.delete = _delete
        self.worker.main(args)

    def test_register_simple(self):
        self._run_worker(['register', 'mocked', self.worker_version, 'tag'])
        self.assertTrue(os.path.exists(os.path.join(self.worker_dir, 'cron')))
        host = self.worker.HostProps().data['name']
        self.assertEqual([host], [x.name for x in Host.list()])

    def test_uninstall(self):
        self._run_worker(['register', 'mocked', self.worker_version, 'tag'])
        self._run_worker(['uninstall'])
        self.assertEqual([], list(Host.list()))
        self.assertFalse(os.path.exists(self.worker_dir))

    def test_upgrade(self):
        self._run_worker(['register', 'mocked', 'badversion', 'tag'])
        self._run_worker(['check'])
        config_file = os.path.join(self.worker_dir, 'settings.conf')
        config = ConfigParser()
        config.read([config_file])
        self.assertEqual(self.worker_version, config['bya']['version'])

    def test_update_host(self):
        self._run_worker(['register', 'mocked', self.worker_version, 'tag'])
        self.assertTrue(os.path.exists(self.worker.HostProps.CACHE))
        host = self.worker.HostProps().data['name']
        Host.get(host).update(cpu_type='test')
        props = self.worker.HostProps()
        props.data['cpu_type'] = 'test'
        props.cache()

        # now run a check and it should update it back
        self._run_worker(['check'])
        self.assertNotEqual('test', Host.get(host).cpu_type)

    def _create_run(self):
        jobname = 'jobname_foo'
        self._write_job(jobname, self.jobdef)
        j = jobs.find_jobdef(jobname)
        j.create_build([{'name': 'foo', 'container': 'busybox'}])

    def test_getrun(self):
        self._create_run()
        self._run_worker(['register', 'mocked', self.worker_version, 'tag'])
        self.hits = 0

        def run(run):
            self.hits += 1
        self.worker.Runner.execute = run
        self._run_worker(['check'])
        self.assertEqual(1, self.hits)

    def test_noruns(self):
        self._create_run()
        self._run_worker(['register', 'mocked', self.worker_version, 'tag'])

        # fake out a full number of concurrent runs
        p = os.path.join(self.worker_dir, 'runs')
        os.mkdir(p)
        os.mkdir(os.path.join(p, 'run1'))
        os.mkdir(os.path.join(p, 'run2'))
        self.hits = 0

        def run(run):
            self.hits += 1
        self.worker.Runner.execute = run
        self._run_worker(['check'])
        self.assertEqual(0, self.hits)

    def test_execute_run(self):
        self._create_run()
        self._run_worker(['register', 'mocked', self.worker_version, 'tag'])
        self.hits = 0

        def run(run):
            self.hits += 1
        self.worker.Runner.execute = run
        self._run_worker(['check'])
        self.assertEqual(1, self.hits)
