from flask import flash, redirect, render_template, request, url_for
import flask_login

from bya.user import User
from bya.views import app, login_manager


@login_manager.user_loader
def user_loader(username):
    return User.get(username)


@login_manager.request_loader
def request_loader(request):
    u = User.get(request.form.get('user'))
    if u is None:
        return
    u.authenticate(request.form['password'])
    return u


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        error = 'Invalid Credentials. Please try again.'
        user = User.get(request.form['user'])
        if user and user.authenticate(request.form['password']):
            flask_login.login_user(user)
            flash('Logged in successfully')
            return redirect(request.args.get('next') or url_for('index'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    flask_login.logout_user()
    return redirect(url_for('index'))
