'''
app - package
====================
'''

# standard
import os.path

# pypi
from flask import Flask, send_from_directory, g, session, request, render_template, current_app
from jinja2 import ChoiceLoader, PackageLoader
from sqlalchemy import select
from sqlalchemy.exc import NoReferencedTableError, ProgrammingError
import loutilities
from loutilities.configparser import getitems

# homegrown
from .model import Race

appname = 'tm-csv-connector'

# define security globals
user_datastore = None
security = None

# hold application here
app = None

# create application
def create_app(config_obj, configfiles=None, init_for_operation=True):
    '''
    apply configuration object, then configuration files
    '''
    global app
    # can't have hyphen in package name, so need to specify with underscore
    app = Flask(appname.replace('-', '_'))
    app.config.from_object(config_obj)
    if configfiles:
        for configfile in configfiles:
            appconfig = getitems(configfile, 'app')
            app.config.update(appconfig)
    
    # tell jinja to remove linebreaks
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    # define product name (don't import nav until after app.jinja_env.globals['_productname'] set)
    app.jinja_env.globals['_productname'] = app.config['THISAPP_PRODUCTNAME']
    app.jinja_env.globals['_productname_text'] = app.config['THISAPP_PRODUCTNAME_TEXT']

    # initialize database
    from .model import db
    db.init_app(app)

    # # initialize uploads
    # if init_for_operation:
    #     init_uploads(app)

    # handle <interest> in URL - https://flask.palletsprojects.com/en/1.1.x/patterns/urlprocessors/
    @app.url_value_preprocessor
    def pull_interest(endpoint, values):
        try:
            g.interest = values.pop('interest', None)
        except AttributeError:
            g.interest = None
        finally:
            if not g.interest:
                g.interest = request.args.get('interest', None)

    # add loutilities tables-assets for js/css/template loading
    # see https://adambard.com/blog/fresh-flask-setup/
    #    and https://webassets.readthedocs.io/en/latest/environment.html#webassets.env.Environment.load_path
    # loutilities.__file__ is __init__.py file inside loutilities; os.path.split gets package directory
    loutilitiespath = os.path.join(os.path.split(loutilities.__file__)[0], 'tables-assets', 'static')

    @app.route('/loutilities/static/<path:filename>')
    def loutilities_static(filename):
        return send_from_directory(loutilitiespath, filename)

    # bring in js, css assets here, because app needs to be created first
    from .assets import asset_env, asset_bundles
    with app.app_context():
        # is database available?
        database_available = True
        try:
            # races = db.session.scalars(select(Race))
            races = Race.query.all()
        except (NoReferencedTableError, ProgrammingError):
            database_available = False
    
        # g.loutility needs to be set before update_local_tables called and before UserSecurity() instantiated (not done this app)
        # g.loutility = app.config['APP_LOUTILITY']

        # js/css files
        asset_env.append_path(app.static_folder)
        asset_env.append_path(loutilitiespath, '/loutilities/static')

        # templates
        loader = ChoiceLoader([
            app.jinja_loader,
            PackageLoader('loutilities', 'tables-assets/templates')
        ])
        app.jinja_loader = loader

    # initialize assets
    asset_env.init_app(app)
    asset_env.register(asset_bundles)

    # Set up Flask-Security and views if database is available
    if database_available:

        # activate views
        from .views.public import bp as public
        app.register_blueprint(public)

    # need to force app context else get
    #    RuntimeError: Working outside of application context.
    #    RuntimeError: Attempted to generate a URL without the application context being pushed.
    # see http://kronosapiens.github.io/blog/2014/08/14/understanding-contexts-in-flask.html
    with app.app_context():
        # import navigation after views created
        from . import nav

        # # turn on logging
        # from .applogging import setlogging
        # setlogging()
        
        # set up scoped session
        from sqlalchemy.orm import scoped_session, sessionmaker
        # see https://github.com/pallets/flask-sqlalchemy/blob/706982bb8a096220d29e5cef156950237753d89f/flask_sqlalchemy/__init__.py#L990
        # use binds if defined
        if 'SQLALCHEMY_BINDS' in app.config and app.config['SQLALCHEMY_BINDS']:
            db.session = scoped_session(sessionmaker(autocommit=False,
                                                    autoflush=False,
                                                    binds=db.get_binds()
                                                    ))
        else:
            db.session = scoped_session(sessionmaker(autocommit=False,
                                                    autoflush=False,
                                                    bind=db.get_engine(),
                                                    ))
        db.query = db.session.query_property()

        # # handle favicon request for old browsers
        # app.add_url_rule('/favicon.ico', endpoint='favicon',
        #                 redirect_to=url_for('static', filename='favicon.ico'))

    # # ----------------------------------------------------------------------
    @app.before_request
    def before_request():
        # g.loutility = Application.query.filter_by(application=app.config['APP_LOUTILITY']).one_or_none()

        # used in layout.jinja2
        # races = db.session.scalars(select(Race).order_by(Race.date.desc())).all()
        races = Race.query.all()
        app.jinja_env.globals['races'] = [{'id': r.id, 'raceyear': r.raceyear} for r in races]


    # # ----------------------------------------------------------------------
    # @app.after_request
    # def after_request(response):
    #     # # check if there are any changes needed to LocalUser table
    #     # userupdated = User.query.order_by(desc('updated_at')).first().updated_at
    #     # localuserupdated = LocalUser.query.order_by(desc('updated_at')).first().updated_at
    #     # interestupdated = Interest.query.order_by(desc('updated_at')).first().updated_at
    #     # localinterestupdated = LocalInterest.query.order_by(desc('updated_at')).first().updated_at
    #     # if userupdated > localuserupdated or interestupdated > localinterestupdated:
    #     #     update_local_tables()

    #     if not app.config['DEBUG']:
    #         app.logger.info(f'{request.remote_addr}: {request.method} {request.url} {response.status_code}')
    #         # debug
    #         # app.logger.info(f'request.headers:\n{request.headers}')
        
    #     return response

    # app back to caller
    return app




