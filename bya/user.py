import grp
import pwd

import pam


class User(object):
    @classmethod
    def get(clazz, name):
        if name is None:
            return None
        try:
            pwd.getpwnam(name)
            return clazz(name)
        except KeyError:
            return None

    def __init__(self, name):
        self.id = name
        self.is_anonymouse = False
        self.is_authenticated = True
        self.is_active = True

    def get_id(self):
        return self.id

    def get_groups(self):
        groups = [g.gr_name for g in grp.getgrall() if self.name in g.gr_mem]
        gid = pwd.getpwnam(self.name).pw_gid
        groups.append(grp.getgrgid(gid).gr_name)
        return groups

    def authenticate(self, password):
        p = pam.pam()
        self.is_authenticated = p.authenticate(self.id, password)
        self.is_anonymous = not self.is_authenticated
        return self.is_authenticated

    def __repr__(self):
        return 'User(%s)' % self.id
