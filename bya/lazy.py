import functools
import json
import os


class PropsFile(object):
    '''Makes an easy way to build an object model based on a json/yaml file.

    The properties themselves are lazily loaded, so that I/O isn't required
    until its required.'''

    PROPS = ()

    @classmethod
    def validate(clazz, data):
        errors = []
        for attr, validator, required in clazz.PROPS:
            val = data.get(attr)
            if not val and required:
                errors.append('Missing required attribute: "%s".' % attr)
            elif val:
                r = validator(val)
                if type(r) == str:
                    errors.append(r)
                elif not r:
                    errors.append('Invalid value for "%s".' % attr)
        return errors

    @staticmethod
    def _prop(prop, self):
        if isinstance(self._data, str):
            # lazy load the definition
            with open(self._data) as f:
                self._data = self._loader(f)
        return self._data.get(prop)

    @classmethod
    def _class_init(clazz):
        # a clever way to give us lazy-loadable object properies
        flag = clazz.__name__ + '_fields_set'
        if getattr(clazz, flag, None):
            return
        for p in clazz.PROPS:
            setattr(
                clazz, p[0], property(functools.partial(clazz._prop, p[0])))
        setattr(clazz, flag, True)

    def __init__(self, name, props_file, loader=json.load):
        self._class_init()
        self.name = name
        self._data = props_file
        self._loader = loader

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.name)


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
