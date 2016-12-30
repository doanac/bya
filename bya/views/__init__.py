import flask
import flask_login

app = flask.Flask(__name__)
app.config.from_object('bya.settings')
login_manager = flask_login.LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


import bya.views.user_auth  # NOQA
import bya.views.api  # NOQA
import bya.views.ui  # NOQA
