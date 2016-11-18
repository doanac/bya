import flask

app = flask.Flask(__name__)
app.config.from_object('bya.settings')


import bya.views.api  # NOQA
import bya.views.ui  # NOQA
