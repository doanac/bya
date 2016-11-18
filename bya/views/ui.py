from bya import settings
from bya.views import app


@app.route('/bya_worker.py')
def client_py():
    with open(settings.WORKER_SCRIPT, 'rb') as f:
        return f.read()
