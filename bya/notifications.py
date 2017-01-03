from bya import settings
from bya.lazy import ModelError, Property

log = settings.get_logger()


class EmailNotify(Property):
    def __init__(self):
        super(EmailNotify, self).__init__('email-notify', dict)

    def validate(self, value):
        v = super(EmailNotify, self).validate(value)
        if type(v) != dict:
            raise ModelError(
                'EmailNotify value(%s) must of type dict' % v, 400)
        if not value.get('users'):
            raise ModelError(
                'EmailNotify(%s) must include a "users" attribute' % v, 400)


NOTIFIERS = {
    'email': EmailNotify(),
}


class NotifyProp(Property):
    def __init__(self):
        super(NotifyProp, self).__init__('notify', list, required=False)

    def validate(self, value):
        value = super(NotifyProp, self).validate(value)
        for v in value:
            if type(v) != dict:
                raise ModelError(
                    'notify value(%s) must of type dict' % v, 400)
            t = v.get('type')
            if not t:
                raise ModelError(
                    'notify(%s) must include a "type" attribute' % v, 400)
            notifier = NOTIFIERS.get(t)
            if not notifier:
                raise ModelError(
                    'Notify(%s) does not exist' % t, 400)
            notifier.validate(v)
