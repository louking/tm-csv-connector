'''
blueprint for this folder
'''

from flask import Blueprint

# create blueprint first
bp = Blueprint('admin', __name__.split('.')[0], url_prefix='/admin', static_folder='static/admin', template_folder='templates/admin')

# specific views
from . import home
from . import simulation
from . import userrole
