from daemon import DaemonContext
from daemon.runner import (
    DaemonRunner,
    DaemonRunnerStopFailureError,
    make_pidlockfile,
)

# There are 2 bugs in the base class:
#  open in write mode won't accept "buffering=0" in python3
#  the restart function fails if the service isn't running


class SmartDaemonRunner(DaemonRunner):
    def __init__(self, app, args):
        self.parse_args(args)
        self.app = app
        self.daemon_context = DaemonContext()
        self.daemon_context.stdin = open(app.stdin_path, 'r')
        self.daemon_context.stdout = open(app.stdout_path, 'w')
        if getattr(app, 'stderr_path', None):
            self.daemon_context.stderr = open(app.stderr_path, 'w+')
        else:
            self.daemon_context.stderr = self.daemon_context.stdout

        self.pidfile = None
        if app.pidfile_path is not None:
            self.pidfile = make_pidlockfile(
                app.pidfile_path, app.pidfile_timeout)
        self.daemon_context.pidfile = self.pidfile

    def _smart_stop(self):
        # don't fail if not running
        try:
            self._stop()
        except DaemonRunnerStopFailureError as e:
            print(e)

    def _smart_restart(self):
        self._smart_stop()
        self._start()

    def _status(self):
        if self.pidfile.is_locked():
            print('running: pid=%d' % self.pidfile.read_pid())
        else:
            print('stopped')

    action_funcs = {
        'start': DaemonRunner._start,
        'stop': _smart_stop,
        'restart': _smart_restart,
        'status': _status,
    }
