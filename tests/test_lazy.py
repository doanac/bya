import json
import os

from tests import TempDirTest
from bya.lazy import PropsFile


class FooModel(PropsFile):
    PROPS = (
        ('required_str', lambda x: type(x) == str, True),
        ('required_int', lambda x: type(x) == int, True),
        ('optional_bool', lambda x: type(x) == bool, False),
    )


class PropsFileTest(TempDirTest):
    def test_simple(self):
        data = {
            'required_str': 'y',
            'required_int': 1,
            'optional_bool': False,
        }
        self.assertEqual([], FooModel.validate(data))

    def test_missing_required(self):
        data = {
            'required_str': 'y',
            'optional_bool': False,
        }
        e = FooModel.validate(data)
        self.assertEqual(1, len(e))
        self.assertEqual('Missing required attribute: "required_int".', e[0])

    def test_invalid(self):
        data = {
            'required_str': 'y',
            'required_int': '1',
            'optional_bool': False,
        }
        e = FooModel.validate(data)
        self.assertEqual(1, len(e))
        self.assertEqual('Invalid value for "required_int".', e[0])

    def test_load(self):
        data = {
            'required_str': 'y',
            'required_int': 1,
        }
        fname = os.path.join(self.tempdir, 'tmp.json')
        with open(fname, 'w') as f:
            json.dump(data, f)

        p = FooModel('pname', fname)
        self.assertEqual('pname', p.name)
        self.assertEqual('y', p.required_str)
        self.assertEqual(1, p.required_int)
