'''
userrole - manage application users and roles
====================================================
'''

# this has been adapted from loutilities.user.views.userrole.py due to embedded
# User and Role models in tm-csv-connector db

# standard

# pypi
from validators.email import email
from flask import g, request
from flask_security import current_user
from flask_security.recoverable import send_reset_password_instructions
from loutilities.tables import DbCrudApiRolePermissions, SEPARATOR, DteDbRelationship
from loutilities.timeu import asctime

# homegrown
from . import bp
from ... import user_datastore
from ...model import db, User, Role
from ...roles import ROLE_SUPER_ADMIN

ymdtime = asctime('%Y-%m-%d %H:%M:%S')
roles_accepted = [ROLE_SUPER_ADMIN]

class ParameterError(Exception):
    '''raise exception if parameter error'''

##########################################################################################
# users endpoint
###########################################################################################

user_dbattrs = 'id,email,name,roles,last_login_at,current_login_at,last_login_ip,current_login_ip,login_count,active'.split(',')
user_formfields = 'rowid,email,name,roles,last_login_at,current_login_at,last_login_ip,current_login_ip,login_count,active'.split(',')
user_dbmapping = dict(zip(user_dbattrs, user_formfields))
user_formmapping = dict(zip(user_formfields, user_dbattrs))

user_formmapping['last_login_at'] = lambda dbrow: ymdtime.dt2asc(dbrow.last_login_at) if dbrow.last_login_at else ''
user_formmapping['current_login_at'] = lambda dbrow: ymdtime.dt2asc(dbrow.current_login_at) if dbrow.current_login_at else ''

def user_validate(action, formdata):
    results = []

    if formdata['email'] and not email(formdata['email']):
        results.append({ 'name' : 'email', 'status' : 'invalid email: correct format is like john.doe@example.com' })

    # check apps which user will have access to
    apps = set()
    if formdata['roles'] and 'id' in formdata['roles'] and formdata['roles']['id'] != '':
        roleidsstring = formdata['roles']['id']
        roleids = roleidsstring.split(SEPARATOR)
        for roleid in roleids:
            thisrole = Role.query.filter_by(id=roleid).one()

    # # this app must be one of user's roles
    # if formdata['active'] == 'yes' and g.loutility not in apps:
    #     # need to use name='roles.id' because this field is _treatment:{relationship}
    #     results.append({'name': 'roles.id', 'status': 'give user at least one role which works for this application'})

    return results

class RolesPicker(DteDbRelationship):
    '''
    pick Roles, but special processing based on ROLE_SUPER_ADMIN, i.e., if not ROLE_SUPER_ADMIN only present
    roles allowed for this application
    '''

    def __init__(self, **kwargs):
        # the args dict has default values for arguments added by this derived class
        # caller supplied keyword args are used to update these
        # all arguments are made into attributes for self by the inherited class
        args = dict(
            tablemodel=User,
            fieldmodel=Role,
            labelfield='name',
            formfield='roles',
            dbfield='roles',
            uselist=True,
        )
        args.update(kwargs)

        # this initialization needs to be done before checking any self.xxx attributes
        super().__init__(**args)

    def allowed_roles(self):
        # create a copy so we're not messing with Application record, no more can be configured than current users'
        allowed_roles = current_user.roles[:]
        return allowed_roles

    def set(self, formrow):
        '''
        if not ROLE_SUPER_ADMIN merge newly set roles with those user can't see
        '''
        # these are the roles from the form, but limited to allowed_roles if not ROLE_SUPER_ADMIN
        resultroles = super().set(formrow)
        if not current_user.has_role(ROLE_SUPER_ADMIN):
            theuser = User.query.filter_by(email=formrow['email']).one_or_none()
            allowed_roles = self.allowed_roles()
            if theuser:
                otherroles = [r for r in theuser.roles if r not in allowed_roles]
                resultroles += otherroles
        return resultroles

    def get(self, dbrow_or_id):
        '''
        if not ROLE_SUPER_ADMIN only return roles allowed for this user
        '''
        rv = super().get(dbrow_or_id)
        rvnames = rv['name'].split(SEPARATOR)
        rvids = rv['id'].split(SEPARATOR)
        if not current_user.has_role(ROLE_SUPER_ADMIN):
            allowed_roles = self.allowed_roles()
            allowed_role_names = [r.name for r in allowed_roles]
            allowed_role_ids = [str(r.id) for r in allowed_roles]
            rv = {
                'name': SEPARATOR.join([item for item in rvnames if item in allowed_role_names]),
                'id': SEPARATOR.join([item for item in rvids if item in allowed_role_ids])
            }
        return rv

    def options(self):
        '''limit visible options to what user can see if not ROLE_SUPER_ADMIN'''
        opts = super().options()
        if not current_user.has_role(ROLE_SUPER_ADMIN):
            allowed_roles = self.allowed_roles()
            allowed_role_ids = [r.id for r in allowed_roles]
            opts = [o for o in opts if o['value'] in allowed_role_ids]
        return opts


class UserCrudApi(DbCrudApiRolePermissions):
    '''
    extends DbCrudApiRolePermissions to manage user for single sign-on with flask-security

    Additional parameters for this class:

    :param user_datastore: return value from flask_security.SQLAlchemyUserDatastore(db, User, Role), which needs
        to be called from application using single sign-on
    '''

    def __init__(self, **kwargs):
        # the args dict has default values for arguments added by this derived class
        # caller supplied keyword args are used to update these
        # all arguments are made into attributes for self by the inherited class
        args = dict(
                    user_datastore=None,
                    )
        args.update(kwargs)

        # this initialization needs to be done before checking any self.xxx attributes
        super().__init__(**args)

        if not self.user_datastore:
            raise ParameterError('user_datastore required')

    def createrow(self, formdata):
        '''
        createrow is used by create form, may need to also send password reset request to user.
        comes from tables-assets/static/user/admin/beforedatatables.js user_create_send_notification_button()

        :param formdata: data from form
        :return:
        '''
        # create the user
        email = formdata['email']
        name = formdata['name']
        roles = [Role.query.filter_by(id=id).one() for id in formdata['roles']['id'].split(SEPARATOR)]
        newuser = self.user_datastore.create_user(email=email, name=name,
                                                  roles=roles)

        # force id to be set. required for response data and password reset
        db.session.flush()

        # return the newly created row
        row = self.dte.get_response_data(newuser)

        # admin may have requested password reset email be sent to the user
        if 'resetpw' in request.form:
            send_reset_password_instructions(newuser)

        return row

    def check_superadmin(self, col):
        '''
        check if col should be included in display based on user's roles

        :param col: column to check
        :return: True if column should be included
        '''
        rv = True
        if not current_user.has_role(ROLE_SUPER_ADMIN):
            supercols = ['last_login_at', 'last_login_ip', 'current_login_ip', 'login_count']
            colname = col['name'].split('.')[0]
            if colname in supercols:
                rv = False
        return rv

    def getdtoptions(self):
        '''limit columns to those this user is allowed to see'''
        dtoptions = super().getdtoptions()
        dtoptions['columns'] = [c for c in dtoptions['columns'] if self.check_superadmin(c)]
        return dtoptions

    def getedoptions(self):
        '''limit form fields to those this user is allowed to see'''
        edoptions = super().getedoptions()
        edoptions['fields'] = [c for c in edoptions['fields'] if self.check_superadmin(c)]
        return edoptions

    def updaterow(self, thisid, formdata):
        '''
        updaterow is used by edit form, may need to also send password reset request to user.
        comes from tables-assets/static/user/admin/beforedatatables.js reset_password_button()

        :param thisid: id of user
        :param formdata: edit form
        :return: row data
        '''
        if 'resetpw' in request.form:
            user = User.query.filter_by(id=thisid).one()
            send_reset_password_instructions(user)
        return super().updaterow(thisid, formdata)

class UserView(UserCrudApi):
    def __init__(self, **kwargs):
        '''
        application MUST instantiate UserView
        '''
        self.kwargs = kwargs
        args = dict(
            app=bp,  # use blueprint instead of app
            db=db,
            model=User,
            # version_id_col='version_id',  # optimistic concurrency control
            roles_accepted=roles_accepted,
            template='datatables.jinja2',
            pagename='users',
            endpoint='admin.users',
            rule='/users',
            dbmapping=user_dbmapping,
            formmapping=user_formmapping,
            clientcolumns=[
                {'data': 'email', 'name': 'email', 'label': 'Email', '_unique': True,
                 'className': 'field_req',
                 },
                {'data': 'name', 'name': 'name', 'label': 'Full Name',
                 'className': 'field_req',
                 },
                {'data': 'roles', 'name': 'roles', 'label': 'Roles',
                 '_treatment': {'relationship': {'optionspicker': RolesPicker()}}
                 },
                {'data': 'active', 'name': 'active', 'label': 'Active',
                 '_treatment': {'boolean': {'formfield': 'active', 'dbfield': 'active'}},
                 'ed': {'def': 'yes'},
                 },
                {'data': 'last_login_at', 'name': 'last_login_at', 'label': 'Last Login At',
                 'className': 'dt-body-nowrap',
                 'type': 'readonly'
                 },
                {'data': 'current_login_at', 'name': 'current_login_at', 'label': 'Current Login At',
                 'className': 'dt-body-nowrap',
                 'type': 'readonly',
                 },
                {'data': 'last_login_ip', 'name': 'last_login_ip', 'label': 'Last Login IP', 'type': 'readonly'},
                {'data': 'current_login_ip', 'name': 'current_login_ip', 'label': 'Current Login IP',
                 'type': 'readonly'
                 },
                {'data': 'login_count', 'name': 'login_count', 'label': 'Login Count', 'type': 'readonly'},
            ],
            validate=user_validate,
            servercolumns=None,  # not server side
            idSrc='rowid',
            buttons=[{
                         'extend': 'create',
                         'editor': {'eval': 'editor'},
                         'formButtons': [
                             {'text': 'Create and Send', 'action': {'eval': 'user_create_send_notification_button'}},
                             {'text': 'Create', 'action': {'eval': 'submit_button'}},
                         ]
                     },
                     {
                         'extend': 'editRefresh',
                         'text': 'Edit',
                         'editor': {'eval': 'editor'},
                         'formButtons': [
                             {'text': 'Reset Password', 'action': {'eval': 'reset_password_button'}},
                             {'text': 'Update', 'action': {'eval': 'submit_button'}},
                         ]
                     },
            ],
            dtoptions={
                'scrollCollapse': True,
                'scrollX': True,
                'scrollXInner': "100%",
                'scrollY': True,
            },
        )
        args.update(kwargs)
        super().__init__(**args)

user_view = UserView(
    user_datastore=user_datastore,
)
user_view.register()

##########################################################################################
# roles endpoint
###########################################################################################

role_dbattrs = 'id,name,description'.split(',')
role_formfields = 'rowid,name,description'.split(',')
role_dbmapping = dict(zip(role_dbattrs, role_formfields))
role_formmapping = dict(zip(role_formfields, role_dbattrs))

class RoleView(DbCrudApiRolePermissions):
    def __init__(self, **kwargs):
        '''
        application MUST instantiate RoleView
        '''
        self.kwargs = kwargs
        args = dict(
                    app = bp,   # use blueprint instead of app
                    db = db,
                    model = Role, 
                    # version_id_col = 'version_id',  # optimistic concurrency control
                    roles_accepted = roles_accepted,
                    template = 'datatables.jinja2',
                    pagename = 'roles', 
                    endpoint = 'admin.roles',
                    rule = '/roles',
                    dbmapping = role_dbmapping, 
                    formmapping = role_formmapping, 
                    clientcolumns = [
                        { 'data': 'name', 'name': 'name', 'label': 'Name',
                          'className': 'field_req',
                          },
                        { 'data': 'description', 'name': 'description', 'label': 'Description' },
                    ],
                    servercolumns = None,  # not server side
                    idSrc = 'rowid', 
                    buttons = ['create', 'editRefresh', 'remove'],
                    dtoptions = {
                                        'scrollCollapse': True,
                                        'scrollX': True,
                                        'scrollXInner': "100%",
                                        'scrollY': True,
                                  },
                    )
        args.update(kwargs)
        super().__init__(**args)

role_view = RoleView()
role_view.register()
