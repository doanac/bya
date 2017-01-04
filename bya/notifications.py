import smtplib

from email.mime.text import MIMEText

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

    def send_mail(self, addrs, subject, body):
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = settings.EMAIL_NOTIFY_FROM
        msg['To'] = addrs

        s = smtplib.SMTP('localhost')
        s.send_message(msg)
        s.quit()

    def notify(self, props, jobdef, build, status):
        subject = 'BYA Build: %s #%d: %s' % (jobdef.name, build.number, status)
        url = '= https://%s/%s.job/builds/%s/' % (
            settings.SERVER_NAME, build.name.replace('#', '/'), build.number)
        body = '%s\n%s\n' % (url, build.summary)
        self.send_mail(props['users'], subject, body)


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

    @staticmethod
    def notify_build(jobdef, build, status):
        notifiers = jobdef.notify or []
        for x in notifiers:
            if not x.get('only_failures') or status != 'Completed':
                NOTIFIERS[x['type']].notify(x, jobdef, build, status)
