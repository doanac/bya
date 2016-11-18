import importlib.util
import json as jsonlib
import os
import shutil

from tests import ModelTest

from bya.models import Host
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

    def _run_worker(self, args):
        args = self.worker.get_args(args)
        args.server.CRON_FILE = os.path.join(self.worker_dir, 'cron')

        def _post(resource, json):
            data = jsonlib.dumps(json)
            return self.app.post(
                resource, data=data, content_type='application/json')

        def _delete(resource, headers):
            return self.app.delete(resource, headers=headers)
        args.server.requests.post = _post
        args.server.requests.delete = _delete
        self.worker.main(args)

    def test_register_simple(self):
        self._run_worker(['register', 'mocked', '12'])
        self.assertTrue(os.path.exists(os.path.join(self.worker_dir, 'cron')))
        host = self.worker.HostProps().data['name']
        self.assertEqual([host], [x.name for x in Host.list()])

    def test_uninstall(self):
        self._run_worker(['register', 'mocked', '12'])
        self._run_worker(['uninstall'])
        self.assertEqual([], list(Host.list()))
        self.assertFalse(os.path.exists(self.worker_dir))
