'''pytest setup for the app tests (#166)

The tests run in the dev app container, against a separate `tm-csv-connector-test` database in the
`db` container, which is dropped and rebuilt from the models at the start of each run. The dev
database and the real output CSV aren't touched: OUTPUT_DIR is a temporary directory. See
CLAUDE.md for how to run them.

The app is created once per run, in normal mode. Each test starts with empty tables, except the
users and roles that create_app() set up.

`--sim` runs the simulation-mode tests in tests/sim instead (#167). The blueprints and db.session are
module-level, so a run can create only one app, in one mode. Without `--sim`, tests/sim is skipped.
'''
# standard
import os
from pathlib import Path

# pypi
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from loutilities.configparser import getitems

TEST_DBNAME = 'tm-csv-connector-test'
CONFIGFILE = '/config/tm-csv-connector.cfg'
# kept between tests: create_app() sets up the default user, and requests log in as that user
KEEP_TABLES = {'user', 'role', 'roles_users'}
SIMDIR = Path(__file__).parent / 'sim'

def pytest_addoption(parser):
    parser.addoption('--sim', action='store_true',
                     help='run the simulation-mode tests in tests/sim, instead of the normal-mode tests')

def in_simdir(path):
    return path == SIMDIR or SIMDIR in path.parents

def pytest_configure(config):
    # without --sim, tests/sim would be skipped silently
    if not config.getoption('sim') and any(in_simdir(Path(a.split('::')[0]).resolve()) for a in config.args):
        raise pytest.UsageError('the tests in tests/sim run in simulation mode: add --sim')

def pytest_ignore_collect(collection_path, config):
    """collect only tests/sim with --sim, and everything else without it"""
    sim_path = in_simdir(collection_path)
    if config.getoption('sim'):
        # the directories above tests/sim must be collected to reach it
        if not sim_path and collection_path not in SIMDIR.parents:
            return True
    elif sim_path:
        return True
    return None

def root_url(dbname=None):
    with open('/run/secrets/db-password') as f:
        password = f.readline().strip()
    return URL.create('mysql', username='root', password=password, host='db', database=dbname)

def create_test_database():
    """drop and recreate the test database, with tables from the models"""
    engine = create_engine(root_url())
    with engine.begin() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS `{TEST_DBNAME}`'))
        conn.execute(text(f'CREATE DATABASE `{TEST_DBNAME}`'))
    engine.dispose()

    # import here, so the test database exists before anything connects to it
    from tm_csv_connector.model import db
    engine = create_engine(root_url(TEST_DBNAME))
    db.metadata.create_all(engine)
    engine.dispose()

class TestConfig:
    """the dev cfg's [app] section, with the test database, in normal or simulation mode"""
    def __init__(self, output_dir, simulation_mode=False):
        from tm_csv_connector.settings import Config
        for key in dir(Config):
            if key.isupper():
                setattr(self, key, getattr(Config, key))
        for key, value in getitems(CONFIGFILE, 'app').items():
            setattr(self, key, value)
        self.SQLALCHEMY_DATABASE_URI = root_url(TEST_DBNAME).render_as_string(hide_password=False)
        self.SIMULATION_MODE = simulation_mode
        if simulation_mode:
            # these come from the sim overlay's secrets, which the dev container doesn't have
            self.USER_SUPERADMIN_PW = 'test super-admin password'
            self.SECURITY_PASSWORD_SALT = 'test salt'
        self.TESTING = True
        self.WTF_CSRF_ENABLED = False
        self.SQLALCHEMY_ECHO = False
        self.OUTPUT_DIR = str(output_dir)

@pytest.fixture(scope='session')
def output_dir(tmp_path_factory):
    return tmp_path_factory.mktemp('output_dir')

@pytest.fixture(scope='session')
def simulation_mode(request):
    return request.config.getoption('sim')

@pytest.fixture(scope='session')
def app(output_dir, simulation_mode):
    # the sim overlay sets SIMULATION_MODE in the container's environment, which create_app() honors
    os.environ.pop('SIMULATION_MODE', None)
    create_test_database()

    from tm_csv_connector import create_app
    app = create_app(TestConfig(output_dir, simulation_mode), init_for_operation=True)
    assert app.config['SIMULATION_MODE'] == simulation_mode
    # the dev cfg must not have leaked the real database in
    assert TEST_DBNAME in app.config['SQLALCHEMY_DATABASE_URI']
    return app

@pytest.fixture(autouse=True)
def clean_tables(app):
    """give each test empty tables, and check it left filelock unlocked"""
    from tm_csv_connector.model import db
    from tm_csv_connector.fileformat import filelock
    yield
    held = filelock.locked()
    if held:
        filelock.release()
    with app.app_context():
        db.session.remove()
        with db.engine.begin() as conn:
            conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))
            # foreign key checks are off, so the order doesn't matter
            for name in db.metadata.tables:
                if name not in KEEP_TABLES:
                    conn.execute(text(f'DELETE FROM `{name}`'))
            conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))
    assert not held, 'test left filelock locked'

@pytest.fixture
def ctx(app):
    """app context for the test body; ORM objects are detached after each request, since the
    request's teardown removes the session, so keep ids and query again"""
    with app.app_context():
        yield

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def outfile(app, output_dir, ctx):
    """turn on the output file setting; returns the file's path"""
    from tm_csv_connector.model import db, Setting
    db.session.add(Setting(name='output-file', value='results.csv'))
    db.session.commit()
    path = output_dir / 'results.csv'
    if path.exists():
        path.unlink()
    yield path
    if path.exists():
        path.unlink()
