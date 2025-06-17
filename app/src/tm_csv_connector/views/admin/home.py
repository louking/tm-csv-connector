'''
home - administrative views
=================================
'''

# pypi
from flask import render_template
from flask.views import MethodView
from flask_security import auth_required

# homegrown
from . import bp

#######################################################################
class AdminHome(MethodView):
    decorators = [auth_required()]

    def get(self):
        return render_template('home.jinja2',
                               pagename='Admin Home',
                               url_rule='/admin',
                               )

admin_view = AdminHome.as_view('home')
bp.add_url_rule('/', view_func=admin_view, methods=['GET',])

