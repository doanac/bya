import functools
import json
import os


class ModelError(Exception):
    def __init__(self, msg, code=500):
        super(ModelError, self).__init__(msg)
        self.status_code = code


class Property(object):
    def __init__(self, name, data_type, def_value=None, required=True):
        self.name = name
        self.required = required
        self.def_value = def_value
        self.data_type = data_type
        if def_value:
            self.validate(def_value)

    def validate(self, value):
        if value is None and self.required:
            raise ModelError(
                'Property(%s) must not be None' % self.name, 400)
        if value is not None and type(value) != self.data_type:
            raise ModelError(
                'Property(%s) must be: %r' % (self.name, self.data_type), 400)
        return value


class StrChoiceProperty(Property):
    def __init__(self, name, vals, def_value=None):
        self.vals = vals
        super(StrChoiceProperty, self).__init__(
            name, str, def_value, not def_value)

    def validate(self, value):
        if value not in self.vals:
            raise ModelError(
                'Property(%s) must be in: %r' % (self.name, self.vals), 400)
        return value


class PropsFile(object):
    '''Makes an easy way to build an object model based on a json/yaml file.

    The properties themselves are lazily loaded, so that I/O isn't required
    until its required.'''

    PROPS = ()

    @classmethod
    def validate(clazz, data):
        for prop in clazz.PROPS:
            val = data.get(prop.name)
            if not val and prop.required:
                raise ModelError(
                    'Missing required attribute: "%s".' % prop.name)
            elif val:
                data[prop.name] = prop.validate(val)

    @staticmethod
    def _prop(prop, self):
        if self._data is None:
            # lazy load the definition
            with open(self._file) as f:
                self._data = self._loader(f)
        v = self._data.get(prop)
        if not v:
            for p in self.PROPS:
                if p.name == prop:
                    return p.def_value
        return v

    @classmethod
    def _class_init(clazz):
        # a clever way to give us lazy-loadable object properies
        flag = clazz.__name__ + '_fields_set'
        if getattr(clazz, flag, None):
            return
        for prop in clazz.PROPS:
            setattr(clazz, prop.name,
                    property(functools.partial(clazz._prop, prop.name)))
        setattr(clazz, flag, True)

    def __init__(self, name, props_file, loader=json.load):
        self._class_init()
        self.name = name
        self._file = props_file
        self._data = None
        self._loader = loader

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.name)

    def update(self, **kwargs):
        with open(self._file) as f:
            orig = self._loader(f)
        orig.update(kwargs)
        self.validate(orig)
        with open(self._file, 'w') as f:
            json.dump(orig, f)


class PropsDir(PropsFile):
    '''Same as a PropsFile but the object lives in a directory so other
    artifacts can be stored with it'''

    def __init__(self, path, loader=json.load):
        fname = os.path.join(path, 'props')
        name = os.path.basename(path)
        super(PropsDir, self).__init__(name, fname, loader)
        self.path = path

    def open_file(self, name, mode='r'):
        return open(os.path.join(self.path, name), mode)

    @classmethod
    def create(clazz, path, data):
        errs = clazz.validate(data)
        if errs:
            return errs
        if not os.path.exists(path):
            os.mkdir(path)
        with open(os.path.join(path, 'props'), 'w') as f:
            json.dump(data, f)
