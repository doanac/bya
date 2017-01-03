import os
import subprocess

VERSION = None


def _get_version():
    '''return either the tag on HEAD or the shortened commit id if not found'''
    out = subprocess.check_output(['git', 'log', '--format=%h %d', '-1'],
                                  cwd=os.path.dirname(__file__)).decode()
    version, ref_names = out.split('(')
    return version.strip()

try:
    VERSION = _get_version()
except:
    VERSION = '???'
