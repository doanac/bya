import json
import os

from tests import TempDirTest
from bya.lazy import ModelError, PropsFile, PropsDir, Property


class FooModel(PropsFile):
    PROPS = (
        Property('required_str', str),
        Property('required_int', int),
        Property('optional_bool', bool, True, False),
    )


class BarModel(PropsDir):
    PROPS = (Property('required_str', str),)


class PropsFileTest(TempDirTest):
    def test_simple(self):
        data = {
            'required_str': 'y',
            'required_int': 1,
            'optional_bool': False,
        }
        FooModel.validate(data)

    def test_missing_required(self):
        data = {
            'required_str': 'y',
            'optional_bool': False,
        }
        msg = 'Missing required attribute: "required_int".'
        with self.assertRaisesRegex(ModelError, msg):
            FooModel.validate(data)

    def test_invalid(self):
        data = {
            'required_str': 'y',
            'required_int': '1',
            'optional_bool': False,
        }
        msg = "Property\(required_int\) must be: <class 'int'>"
        with self.assertRaisesRegex(ModelError, msg):
            FooModel.validate(data)

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
        self.assertTrue(p.optional_bool)

    def test_does_not_exist(self):
        with self.assertRaisesRegex(ModelError, 'pname does not exist'):
            FooModel('pname', 'path does not exist')


class PropsDirTest(TempDirTest):
    def test_simple(self):
        data = {'required_str': 'y'}
        fname = os.path.join(self.tempdir, 'props')
        with open(fname, 'w') as f:
            json.dump(data, f)

        p = BarModel(self.tempdir)
        self.assertEqual('y', p.required_str)
        with p.open_file('blah', 'w') as f:
            f.write('testing')
        with p.open_file('blah') as f:
            self.assertEqual('testing', f.read())
