from bya.lazy import ModelError, Property


class Trigger(object):
    @classmethod
    def validate(clazz, value):
        for x in clazz.ATTRS:
            if not value.get(x):
                raise ModelError(
                    'Missing attribute "%s" in %s' % (x, value), 400)


class GitTrigger(Property):
    def __init__(self):
        super(GitTrigger, self).__init__('git-trigger', dict)

    def validate(self, value):
        v = super(GitTrigger, self).validate(value)
        if type(v) != dict:
            raise ModelError('GitTrigger value(%s) must of type dict' % v, 400)
        if not value.get('http_url'):
            raise ModelError(
                'GitTrigger(%s) must include an "http_url" attribute' % v, 400)
        refs = value.get('refs')
        if not refs or type(refs) != list:
            raise ModelError(
                'GitTrigger(%s) must include a non-empty list "refs"', 400)
        for ref in refs:
            if not ref.startswith('refs/'):
                raise ModelError(
                    'GitTrigger(%s) refs must start with "refs/"', 400)

TRIGGERS = {
    'git': GitTrigger(),
}


class TriggerProp(Property):
    def __init__(self):
        super(TriggerProp, self).__init__('triggers', list)

    def validate(self, value):
        value = super(TriggerProp, self).validate(value)
        for v in value:
            if type(v) != dict:
                raise ModelError(
                    'Trigger value(%s) must of type dict' % v, 400)
            t = v.get('type')
            if not t:
                raise ModelError(
                    'Trigger(%s) must include a "type" attribute' % v, 400)
            trigger = TRIGGERS.get(t)
            if not trigger:
                raise ModelError(
                    'Trigger(%s) does not exist' % t, 400)
            trigger.validate(v)
