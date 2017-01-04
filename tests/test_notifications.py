import os

from bya import settings

from tests import ModelTest

from unittest.mock import patch


class TestNotifications(ModelTest):
    def setUp(self):
        super(TestNotifications, self).setUp()
        self.jobdef['notify'] = [
            {
                'type': 'email',
                'users': ['1@1.com', '2@2.com'],
            },
        ]
        os.mkdir(os.path.join(settings.BUILDS_DIR, 'name'))

    @patch('bya.notifications.EmailNotify.send_mail')
    def test_simple(self, send_mail):
        self._write_job('name', self.jobdef)
        b = self._load_job('name').create_build(
            [{'name': 'foo', 'container': 'ubuntu'}])

        # complete the run
        r = list(b.list_runs())[0]
        r.update(status='PASSED')
        self.assertEqual(1, send_mail.call_count)
        self.assertEqual(
            'BYA Build: name #1: Completed', send_mail.call_args[0][1])
        self.assertIn('name.job/builds/1/', send_mail.call_args[0][2])

    @patch('bya.notifications.EmailNotify.send_mail')
    def test_no_email_on_pass(self, send_mail):
        self.jobdef['notify'][0]['only_failures'] = True
        self._write_job('name', self.jobdef)
        b = self._load_job('name').create_build(
            [{'name': 'foo', 'container': 'ubuntu'}])

        # complete the run
        r = list(b.list_runs())[0]
        r.update(status='PASSED')
        self.assertEqual(0, send_mail.call_count)

    @patch('bya.notifications.EmailNotify.send_mail')
    def test_email_on_fail(self, send_mail):
        self.jobdef['notify'][0]['only_failures'] = True
        self._write_job('name', self.jobdef)
        b = self._load_job('name').create_build(
            [{'name': 'foo', 'container': 'ubuntu'}])

        # complete the run
        r = list(b.list_runs())[0]
        r.update(status='FAILED')
        self.assertEqual(1, send_mail.call_count)
        self.assertEqual('BYA Build: name #1: Completed with Failure(s)',
                         send_mail.call_args[0][1])
