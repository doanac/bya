import os

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    Response,
)
from flask_login import current_user

from bya import settings
from bya.models import (
    jobs,
    Host,
    ModelError,
    RunQueue,
)
from bya.version import VERSION
from bya.views import app
CSS_ACTIVE = 'pure-menu-selected'


@app.context_processor
def inject_version():
    return dict(bya_revno=VERSION)


@app.errorhandler(ModelError)
def _app_error_handler(err):
    msg = str(err)
    if err.status_code == 404:
        msg = 'Job Group(%s) does not exist' % request.path
    content = '<h1>HTTP %d ERROR</h1><pre>%s</pre>' % (err.status_code, msg)
    return content, err.status_code


@app.route('/')
def index():
    return job_group()


@app.route('/hosts/')
def hosts():
    return render_template(
        'hosts.html', host_css_active=CSS_ACTIVE, hosts=Host.list())


@app.route('/queues/')
def queues():
    running = {}
    queued = {}
    for run in RunQueue.list_running():
        b = run.get_build()
        run.jobname = b.name.replace('#', '/')
        run.buildnum = b.number
        running.setdefault(b, []).append(run)
    for run in RunQueue.list_queued():
        b = run.get_build()
        queued.setdefault(b, []).append(run)
    return render_template('queues.html', queues_css_active=CSS_ACTIVE,
                           running=running, queued=queued)


@app.route('/<name>.job')
@app.route('/<path:jobgroup>/<name>.job')
def job_def(name, jobgroup=None):
    path = name
    if jobgroup:
        path = os.path.join(jobgroup, name)
    job = jobs.find_jobdef(path)
    builds = []
    limit = int(request.args.get('limit', '20'))
    start = int(request.args.get('start', '0'))
    nstart = 0
    for i, b in enumerate(job.list_builds()):
        if i >= start:
            if i < limit + start:
                builds.append(b)
            else:
                nstart = i
                break
    return render_template(
        'job.html', start=nstart, jobgroup=jobgroup, job=job, builds=builds)


@app.route('/<name>.job/builds/<int:build_num>/', methods=['GET', 'POST'])
@app.route('/<path:jobgroup>/<name>.job/builds/<int:build_num>/',
           methods=['GET', 'POST'])
def build(name, build_num, jobgroup=None):
    path = name
    if jobgroup:
        path = os.path.join(jobgroup, name)
    job = jobs.find_jobdef(path)
    build = job.get_build(build_num)
    can_rebuild = job.can_rebuild(current_user)

    if request.method == 'POST':
        if not can_rebuild:
            abort(401)
        job.rebuild(build, current_user.id)
        flash('Queued: %s' % build.name)
        return redirect('queues')

    return render_template('build.html', jobname=name, jobgroup=jobgroup,
                           build=build, trigger_data=build.trigger_data,
                           can_rebuild=can_rebuild)


@app.route('/<name>.job/builds/<int:build_num>/<run>/')
@app.route('/<path:jobgroup>/<name>.job/builds/<int:build_num>/<run>/')
def run(name, build_num, run, jobgroup=None):
    path = name
    if jobgroup:
        path = os.path.join(jobgroup, name)
    run = jobs.find_jobdef(path).get_build(build_num).get_run(run)
    with run.log_fd() as f:
        return Response(f.read(), mimetype='text/plain')


@app.route('/<path:path>/')
def job_group(path=None):
    if path is None:
        g = jobs
    else:
        g = jobs.find_jobgroup(path)
    groups = g.get_groups()
    jobdefs = g.get_jobdefs()
    return render_template('index.html', groups=groups, jobdefs=jobdefs)


@app.route('/bya_worker.py')
def client_py():
    with open(settings.WORKER_SCRIPT, 'rb') as f:
        return f.read()
