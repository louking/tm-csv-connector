'''
app - package
====================
'''

# standard
import os.path

# pypi
from flask import Flask, send_from_directory, g, current_app, render_template, url_for
from flask_mail import Mail
from jinja2 import ChoiceLoader, PackageLoader
from flask_security import SQLAlchemyUserDatastore, Security, hash_password, current_user, login_user
from sqlalchemy import text
from sqlalchemy.exc import NoReferencedTableError, ProgrammingError
from werkzeug.local import LocalProxy
import loutilities
from loutilities.configparser import getitems
from loutilities.flask_helpers.mailer import sendmail

# homegrown
from .version import __version__
from .model import User, Role
from .roles import ROLE_SUPER_ADMIN, ROLE_TMSIM_USER

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

    # hack to add "simulator" to product name in heading
    if app.config.get('SIMULATION_MODE', False):
        app.jinja_env.globals['_productname'] = f"{app.config['THISAPP_PRODUCTNAME']}<span> simulator</span>"
    else:
        # define product name (don't import nav until after app.jinja_env.globals['_productname'] set)
        app.jinja_env.globals['_productname'] = app.config['THISAPP_PRODUCTNAME']
    
    app.jinja_env.globals['_productname_text'] = app.config['THISAPP_PRODUCTNAME_TEXT']
    app.jinja_env.globals['_product_version'] = __version__
    
    # initialize database
    from .model import db
    db.init_app(app)
    
    # # initialize uploads
    # if init_for_operation:
    #     init_uploads(app)

    # add loutilities tables-assets for js/css/template loading
    # see https://adambard.com/blog/fresh-flask-setup/
    #    and https://webassets.readthedocs.io/en/latest/environment.html#webassets.env.Environment.load_path
    # loutilities.__file__ is __init__.py file inside loutilities; os.path.split gets package directory
    loutilitiespath = os.path.join(os.path.split(loutilities.__file__)[0], 'tables-assets', 'static')

    @app.route('/loutilities/static/<path:filename>')
    def loutilities_static(filename):
        return send_from_directory(loutilitiespath, filename)

    # check if default user needs to be automatically logged in
    @app.before_request
    def login_user_no_simulation():
        if not app.config.get('SIMULATION_MODE', False):
            default_user = security.datastore.find_user(email=app.config['USER_DEFAULT_EMAIL'])
            if default_user and not current_user.is_authenticated:
                # log in default user
                # this is needed to set up the session for the user
                current_app.logger.debug(f'Logging in default user: {default_user}')
                login_user(default_user)
                db.session.commit()
    
    # bring in js, css assets here, because app needs to be created first
    from .assets import asset_env, asset_bundles
    with app.app_context():
        # is database available?
        database_available = True
        try:
            # https://stackoverflow.com/a/75547136/799921
            db.session.execute(text('SELECT 1'))
        except (NoReferencedTableError, ProgrammingError):
            database_available = False
    
        # # g.loutility needs to be set before update_local_tables called and before UserSecurity() instantiated
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
        
        for configkey in ['SECURITY_EMAIL_SUBJECT_PASSWORD_RESET',
                        'SECURITY_EMAIL_SUBJECT_PASSWORD_CHANGE_NOTICE',
                        'SECURITY_EMAIL_SUBJECT_PASSWORD_NOTICE',
                        ]:
            app.config[configkey] = app.config[configkey].format(productname=app.config['THISAPP_PRODUCTNAME_TEXT'])

        # Set up Flask-Mail [configuration in <application>.cfg] and security mailer
        mail = Mail(app)

        def security_send_mail(subject, recipient, template, **context):
            # this may be called from view which doesn't reference interest
            # if so pick up user's first interest to get from_email address
            from_email = current_app.config['SECURITY_EMAIL_SENDER']
            # copied from flask_security.utils.send_mail
            if isinstance(from_email, LocalProxy):
                from_email = from_email._get_current_object()
            ctx = ('security/email', template)
            html = render_template('%s/%s.html' % ctx, **context)
            text = render_template('%s/%s.txt' % ctx, **context)
            sendmail(subject, from_email, recipient, html=html, text=text)

        # Set up Flask-Security
        global user_datastore, security
        user_datastore = SQLAlchemyUserDatastore(db, User, Role)
        security = Security(app, user_datastore, send_mail=security_send_mail)

        # admin views are only applicable if in simulation mode
        if app.config.get('SIMULATION_MODE', False):
            # initialize admin views
            from .views.admin import bp as admin
            app.register_blueprint(admin)
        
    # need to force app context else get
    #    RuntimeError: Working outside of application context.
    #    RuntimeError: Attempted to generate a URL without the application context being pushed.
    # see http://kronosapiens.github.io/blog/2014/08/14/understanding-contexts-in-flask.html
    with app.app_context():
        # import navigation after views created
        from . import nav

        # # turn on logging
        from .applogging import setlogging
        setlogging()
        
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

        # set up super-admin user if in simulation mode
        # init for operation False allows the database to be upgraded
        if database_available and init_for_operation:
            if app.config.get('SIMULATION_MODE', False):
                if not security.datastore.find_user(email=app.config['USER_SUPERADMIN_EMAIL']):
                    admin = security.datastore.create_user(email=app.config['USER_SUPERADMIN_EMAIL'], name=app.config['USER_SUPERADMIN_NAME'], password=hash_password(app.config['USER_SUPERADMIN_PW']))
                    security.datastore.find_or_create_role(ROLE_SUPER_ADMIN)
                    db.session.flush()
                    security.datastore.add_role_to_user(admin, ROLE_SUPER_ADMIN)
                    db.session.commit()

            # set up and log in default user if not in simulation mode
            else:
                if not security.datastore.find_user(email=app.config['USER_DEFAULT_EMAIL']):
                    default_user = security.datastore.create_user(email=app.config['USER_DEFAULT_EMAIL'])
                    security.datastore.find_or_create_role(ROLE_TMSIM_USER)
                    db.session.flush()
                    security.datastore.add_role_to_user(default_user, ROLE_TMSIM_USER)
                    db.session.commit()

            
        # # handle favicon request for old browsers
        # app.add_url_rule('/favicon.ico', endpoint='favicon',
        #                 redirect_to=url_for('static', filename='favicon.ico'))

    # app back to caller
    return app




