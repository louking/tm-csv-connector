'''fixtures for the simulation-mode tests (#167); run with `pytest --sim`, see CLAUDE.md

The app comes from tests/conftest.py, which creates it in simulation mode with --sim. create_app()
adds the super admin; the users fixture adds a tmsim admin and a tmsim user. Users and roles are
kept between tests, like the other tables in KEEP_TABLES.
'''
# pypi
import pytest

# homegrown
from tm_csv_connector.model import db, User
from tm_csv_connector.roles import ROLE_SUPER_ADMIN, ROLE_TMSIM_ADMIN, ROLE_TMSIM_USER

from simhelpers import TMSIM_ADMIN, TMSIM_USER

@pytest.fixture(scope='session')
def users(app):
    """{'super': email, 'admin': email, 'user': email}"""
    from tm_csv_connector import user_datastore
    with app.app_context():
        for email, role in [(TMSIM_ADMIN, ROLE_TMSIM_ADMIN), (TMSIM_USER, ROLE_TMSIM_USER)]:
            if not user_datastore.find_user(email=email):
                user = user_datastore.create_user(email=email, name=email.split('@')[0])
                user_datastore.find_or_create_role(role)
                db.session.flush()
                user_datastore.add_role_to_user(user, role)
        db.session.commit()
        superadmin = User.query.filter(User.roles.any(name=ROLE_SUPER_ADMIN)).first()
        assert superadmin, 'create_app() should have added the super admin'
        return {'super': superadmin.email, 'admin': TMSIM_ADMIN, 'user': TMSIM_USER}
