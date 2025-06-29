'''
settings - define default, test and production settings

see http://flask.pocoo.org/docs/1.0/config/?highlight=production#configuration-best-practices
'''

# standard
import logging

# homegrown
from loutilities.configparser import getitems
from . import appname


class Config(object):
    DEBUG = False
    TESTING = False

    # default database
    # https://flask-sqlalchemy.palletsprojects.com/en/2.x/binds/
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_BINDS = {
        'users': 'sqlite:///:memory:',
    }

    # logging
    LOGGING_LEVEL_FILE = logging.INFO
    LOGGING_LEVEL_MAIL = logging.ERROR

    # flask-security configuration -- see https://pythonhosted.org/Flask-Security/configuration.html
    SECURITY_TRACKABLE = True
    SECURITY_DEFAULT_REMEMBER_ME = True

    # avoid warning
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # branding
    THISAPP_PRODUCTNAME = '<span class="brand-all"><span class="brand-left">tm</span><span class="brand-right">tility</span></span>'
    THISAPP_PRODUCTNAME_TEXT = 'tmtility'


class Testing(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False

    # need to set SERVER_NAME to something, else get a RuntimeError about not able to create URL adapter
    # must have following line in /etc/hosts or C:\Windows\System32\drivers\etc\hosts file
    #   127.0.0.1 dev.localhost
    SERVER_NAME = 'dev.localhost'

    # need a default secret key - in production replace by config file
    SECRET_KEY = "<test secret key>"

    # need to allow logins in flask-security. see https://github.com/mattupstate/flask-security/issues/259
    LOGIN_DISABLED = False


class RealDb(Config):
    def __init__(self, configfiles):
        if type(configfiles) == str:
            configfiles = [configfiles]

        # connect to user database based on configuration
        config = {}
        for configfile in configfiles:
            config.update(getitems(configfile, 'database'))
        # https://flask-sqlalchemy.palletsprojects.com/en/2.x/binds/
        dbuser = config['dbuser']
        with open(f'/run/secrets/{appname}-password') as pw:
            password = pw.readline().strip()
        # password = config['dbpassword']
        dbserver = config['dbserver']
        dbname = config['dbname']
        # app.logger.debug(f'mysql://{dbuser}:*******@{dbserver}/{dbname}')
        db_uri = f'mysql://{dbuser}:{password}@{dbserver}/{dbname}'
        self.SQLALCHEMY_DATABASE_URI = db_uri
        # when user database is available, add bind
        if 'usersdbname' in config:
            # https://flask-sqlalchemy.palletsprojects.com/en/2.x/binds/
            usersdbuser = config['usersdbuser']
            with open(f'/run/secrets/users-password') as pw:
                userspassword = pw.readline().strip()
            # userspassword = config['usersdbpassword']
            usersdbserver = config['usersdbserver']
            usersdbname = config['usersdbname']
            usersdb_uri = f'mysql://{usersdbuser}:{userspassword}@{usersdbserver}/{usersdbname}'
            self.SQLALCHEMY_BINDS = {
                'users': usersdb_uri
            }
        
        # set passwords required for simulation mode
        appconfig = {}
        for configfile in configfiles:
            appconfig.update(getitems(configfile, 'app'))
        if appconfig.get('SIMULATION_MODE', False):
            with open(f'/run/secrets/mail-password') as pw:
                mailpw = pw.readline().strip()
                self.MAIL_PASSWORD = mailpw
            with open(f'/run/secrets/super-admin-user-password') as pw:
                sauserpw = pw.readline().strip()
                self.USER_SUPERADMIN_PW = sauserpw
            with open(f'/run/secrets/security-password-salt') as pw:
                securitysaltpw = pw.readline().strip()
                self.SECURITY_PASSWORD_SALT = securitysaltpw

class Development(RealDb):
    DEBUG = True


class Production(RealDb):
    pass


