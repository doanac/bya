import functools
import os

from flask import jsonify, request

from bya import settings
from bya.views import app
from bya.models import (
    Host,
    ModelError,
    Run,
    RunQueue,
)


def _is_host_authenticated(host):
    key = request.headers.get('Authorization', None)
    if key:
        parts = key.split(' ')
        if len(parts) == 2 and parts[0] == 'Token':
            return parts[1] == host.api_key
    return False


def host_authenticated(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('Authorization', None)
        if not key:
            resp = jsonify({'Message': 'No Authorization header provided'})
            resp.status_code = 401
            return resp
        parts = key.split(' ')
        if len(parts) != 2 or parts[0] != 'Token':
            resp = jsonify({'Message': 'Invalid Authorization header'})
            resp.status_code = 401
            return resp
        host = Host.get(kwargs['name'])
        if parts[1] != host.api_key:
            resp = jsonify({'Message': 'Incorrect API key for host'})
            resp.status_code = 401
            return resp
        return f(*args, **kwargs)
    return wrapper


def run_authenticated(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('Authorization', None)
        if not key:
            resp = jsonify({'Message': 'No Authorization header provided'})
            resp.status_code = 401
            return resp
        parts = key.split(' ')
        if len(parts) != 2 or parts[0] != 'Token':
            resp = jsonify({'Message': 'Invalid Authorization header'})
            resp.status_code = 401
            return resp
        run = Run.get(kwargs['bname'], kwargs['bnum'], kwargs['run'])
        if parts[1] != run.api_key:
            resp = jsonify({'Message': 'Incorrect API key for run'})
            resp.status_code = 401
            return resp
        if run.status in (Run.PASSED, Run.FAILED):
            resp = jsonify({'Message': 'Run has completed'})
            resp.status_code = 401
            return resp
        request.run = run
        return f(*args, **kwargs)
    return wrapper


@app.errorhandler(ModelError)
def _model_error_handler(error):
    return str(error) + '\n', error.status_code


@app.route('/api/v1/host/', methods=['GET'])
def host_list():
    return jsonify({'hosts': [x.name for x in Host.list()]})


@app.route('/api/v1/host/', methods=['POST'])
def host_create():
    if 'api_key' not in request.json:
        raise ModelError('Missing required field: api_key')
    request.json['enlisted'] = settings.AUTO_ENLIST_HOSTS
    if 'name' not in request.json:
        raise ModelError('Missing required field: name')
    name = request.json['name']
    del request.json['name']
    Host.create(name, request.json)
    resp = jsonify({})
    resp.status_code = 201
    resp.headers['Location'] = '/api/v1/host/%s/' % name
    return resp


@app.route('/api/v1/host/<string:name>/', methods=['PATCH'])
@host_authenticated
def host_update(name):
    if 'enlisted' in request.json:
        raise ModelError('"enlisted" field cannot be updated via API', 403)

    Host.get(name).update(**request.json)
    return jsonify({})


@app.route('/api/v1/host/<string:name>/', methods=['DELETE'])
@host_authenticated
def host_delete(name):
    Host.get(name).delete()
    return jsonify({})


@app.route('/api/v1/host/<string:name>/', methods=['GET'])
def host_get(name):
    h = Host.get(name)
    h.cpu_type  # force data to be loaded
    h._data['worker_version'] = str(os.stat(settings.WORKER_SCRIPT).st_mtime)
    if _is_host_authenticated(h):
        h.ping()
        avail = int(request.args.get('available_runners'))
        if avail > 0:
            # we could give more than one run, but for now try and give just
            # one and let the runs spread out more amongst workers
            r = RunQueue.take(h.name, h.host_tags.split(','))
            if r:
                h._data['runs'] = [r._data]
    del h._data['api_key']
    return jsonify(h._data)


@app.route('/api/v1/build/<string:bname>/<int:bnum>/<string:run>',
           methods=['POST'])
@run_authenticated
def run_update(bname, bnum, run):
    status = request.headers.get('X-BYA-STATUS')
    if status:
        request.run.update(status=status)
    log_data = request.data.decode()
    if log_data:
        request.run.append_log(log_data)
    return jsonify({})
