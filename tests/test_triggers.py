import os

from bya import settings
from bya.triggers import TriggerManager

from tests import ModelTest

from unittest.mock import Mock, patch


class TestTriggerManager(ModelTest):
    def setUp(self):
        super(TestTriggerManager, self).setUp()
        self.jobdef['triggers'] = [
            {
                'type': 'git',
                'http_url': 'foo',
                'refs': ['refs/heads/master'],
                'runs': [{'name': 'foo', 'container': 'ubuntu'}],
            },
        ]
        self._write_job('name', self.jobdef)
        self.job = self._load_job('name')
        os.mkdir(os.path.join(settings.BUILDS_DIR, 'name'))

    @patch('requests.get')
    def test_simple(self, http_get):
        resp = Mock()
        http_get.return_value = resp
        resp.status_code = 200
        resp.text = '''ignore
ignore
004015f12d4181355604efa7b429fc3bcbae08d27f40 refs/heads/master
004015f12d4181355604efa7b429fc3bcbae08d27f40 refs/pull/123/head
004015f12d4181355604efa7b429fc3bcbae08d27f40 refs/pull/123/head
'''
        mgr = TriggerManager([self.job])
        mgr.run()
        b = self.job.get_last_build()
        r = b.get_run('foo')
        self.assertEqual('ubuntu', r.container)