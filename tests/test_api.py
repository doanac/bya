import json

from tests import ModelTest

from bya.views import app
from bya.models import Host, JobGroup, Run

h1 = {
    'name': 'host_1',
    'distro': 'ubuntu',
    'mem_total': 5,
    'cpu_total': 5,
    'cpu_type': 'arm',
    'api_key': '12345',
    'concurrent_runs': 1,
    'host_tags': 'host1',
}


class ApiTests(ModelTest):

    def setUp(self):
        super(ApiTests, self).setUp()
        app.config['TESTING'] = True
        self.app = app.test_client()

    def post_json(self, url, data, status_code=201, headers=None):
        data = json.dumps(data)
        resp = self.app.post(
            url, data=data, headers=headers, content_type='application/json')
        self.assertEqual(status_code, resp.status_code)
        return resp

    def patch_json(self, url, data, api_key, status_code=200):
        data = json.dumps(data)
        headers = [('Authorization', 'Token ' + api_key)]
        resp = self.app.patch(
            url, data=data, headers=headers, content_type='application/json')
        self.assertEqual(status_code, resp.status_code)

    def get_json(self, url, status_code=200):
        resp = self.app.get(url)
        self.assertEqual(200, resp.status_code)
        return json.loads(resp.data.decode())

    def test_create_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)
        h = list(Host.list())
        self.assertEqual(1, len(h))
        self.assertEqual(h1['name'], h[0].name)
        self.assertEqual(h1['api_key'], h[0].api_key)

        data = self.get_json('/api/v1/host/')
        self.assertEqual(1, len(data['hosts']))
        self.assertEqual('host_1', data['hosts'][0])

    def test_create_host_dup(self):
        self.post_json('/api/v1/host/', h1)
        self.post_json('/api/v1/host/', h1, 409)

    def test_update_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)

        self.patch_json(resp.location, {'cpu_total': 123}, h1['api_key'])
        h = Host.get('host_1')
        self.assertEqual(123, h.cpu_total)

    def test_update_enlisted(self):
        """Ensure hosts can't update this attribute"""
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)
        self.patch_json(resp.location, {'enlisted': True}, h1['api_key'], 403)

    def test_delete_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)

        headers = [('Authorization', 'Token ' + h1['api_key'])]
        resp = self.app.delete(
            resp.location, headers=headers, content_type='application/json')
        self.assertEqual(0, len(list(Host.list())))

    def test_run_update(self):
        self._write_job('name', self.jobdef)
        jobs = JobGroup()
        job = jobs.get_jobdefs()[0]
        build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        run = list(build.list_runs())[0]
        headers = [
            ('Authorization', 'Token ' + run.api_key),
            ('X-BYA-STATUS', Run.PASSED),
        ]
        data = 'logmessage1'
        url = '/api/v1/build/%s/%d/%s' % (build.name, build.number, run.name)
        self.post_json(url, data, status_code=200, headers=headers)
        run = list(build.list_runs())[0]
        self.assertEqual(Run.PASSED, run.status)
        with run.log_fd() as f:
            self.assertIn(data, f.read())

    def test_run_update_no_status(self):
        self._write_job('name', self.jobdef)
        jobs = JobGroup()
        job = jobs.get_jobdefs()[0]
        build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        run = list(build.list_runs())[0]
        headers = [
            ('Authorization', 'Token ' + run.api_key),
        ]
        data = 'logmessage1'
        url = '/api/v1/build/%s/%d/%s' % (build.name, build.number, run.name)
        self.post_json(url, data, status_code=200, headers=headers)
        run = list(build.list_runs())[0]
        self.assertEqual(Run.QUEUED, run.status)
        with run.log_fd() as f:
            self.assertIn(data, f.read())

    def test_run_update_bad_key(self):
        self._write_job('name', self.jobdef)
        jobs = JobGroup()
        job = jobs.get_jobdefs()[0]
        build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        run = list(build.list_runs())[0]
        headers = [
            ('Authorization', 'Token badkey'),
        ]
        data = 'logmessage1'
        url = '/api/v1/build/%s/%d/%s' % (build.name, build.number, run.name)
        self.post_json(url, data, status_code=401, headers=headers)

    def test_run_no_run(self):
        self._write_job('name', self.jobdef)
        jobs = JobGroup()
        job = jobs.get_jobdefs()[0]
        build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        headers = [
            ('Authorization', 'Token badkey'),
        ]
        data = 'logmessage1'
        url = '/api/v1/build/%s/%d/nosuchrun' % (build.name, build.number)
        self.post_json(url, data, status_code=404, headers=headers)

    def test_nested_run(self):
        self._write_job('nested/name', self.jobdef)
        job = JobGroup().find_jobdef('nested/name')
        build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        run = list(build.list_runs())[0]
        headers = [
            ('Authorization', 'Token ' + run.api_key),
        ]
        data = 'logmessage1'
        url = '/api/v1/build/%s/%d/%s' % (build.name, build.number, run.name)
        self.post_json(url, data, status_code=200, headers=headers)
        run = list(build.list_runs())[0]
        self.assertEqual(Run.QUEUED, run.status)
        with run.log_fd() as f:
            self.assertIn(data, f.read())

    def test_run_update_completed(self):
        self._write_job('name', self.jobdef)
        jobs = JobGroup()
        job = jobs.get_jobdefs()[0]
        build = job.create_build([{'name': 'foo', 'container': 'ubuntu'}])
        run = list(build.list_runs())[0]
        run.update(status=Run.PASSED)
        headers = [
            ('Authorization', 'Token ' + run.api_key),
        ]
        data = 'logmessage1'
        url = '/api/v1/build/%s/%d/%s' % (build.name, build.number, run.name)
        self.post_json(url, data, status_code=401, headers=headers)
