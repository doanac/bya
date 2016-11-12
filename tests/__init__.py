import tempfile
import shutil
import unittest


class TempDirTest(unittest.TestCase):
    def setUp(self):
        super(TempDirTest, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
