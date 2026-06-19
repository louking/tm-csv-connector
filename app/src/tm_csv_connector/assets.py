'''
assets - javascript and css asset handling
===================================================
'''

from flask_assets import Bundle, Environment

# jquery
jq_ver = '3.7.1'
jq_ui_ver = '1.14.2'
jq_validate_ver = '1.19.3'

# dataTables
dt_datatables_ver = '2.3.8-pkgs-jqui'

jszip_ver = '2.5.0'

# select2
# NOTE: patch to jquery ui required, see https://github.com/select2/select2/issues/1246#issuecomment-17428249
# currently in datatables.js
s2_ver = '4.0.13'

# smartmenus
sm_ver = '1.2.1'

# yadcf
yadcf_ver = '2.0.1.beta.9.louking.3'
yadcf_suffix = '-2.0'

moment_ver = '2.29.4'       # moment.js (see https://momentjs.com/)
lodash_ver = '4.17.21'      # lodash.js (see https://lodash.com)
d3_ver = '7.4.2'
d3_tip_ver = '1.1'          # https://github.com/VACLab/d3-tip
fa_ver = '6.5.1'            # https://fontawesome.com/
nunjucks_ver = '3.2.0'      # https://mozilla.github.io/nunjucks/
cke_type='classic'           # https://ckeditor.com/ckeditor-5/
cke_ver='26.0.0-members-414' # https://ckeditor.com/ckeditor-5/
materialize_ver='1.0.0'     # https://materializecss.com/
pickadate_ver = '3.6.4'     # https://amsul.ca/pickadate.js/

asset_bundles = {

    'admin_js': Bundle(
        Bundle(f'js/jQuery-{jq_ver}/jquery-{jq_ver}.js', filters='jsmin'),
        Bundle(f'js/jquery-ui-{jq_ui_ver}.custom/jquery-ui.js', filters='jsmin'),

        Bundle(f'js/smartmenus-{sm_ver}/jquery.smartmenus.js', filters='jsmin'),
        Bundle(f'js/lodash-{lodash_ver}/lodash.js', filters='jsmin'),

        Bundle('beforedatatables.js', filters='jsmin'),

        # Bundle('js/JSZip-{ver}/jszip.js'.format(ver=jszip_ver), filters='jsmin'),
        Bundle(f'js/DataTables-{dt_datatables_ver}/datatables.js', filters='jsmin'),
        
        Bundle(f'js/moment-{moment_ver}/js/moment.js', filters='jsmin'),

        Bundle('afterdatatables.js', filters='jsmin'),

        Bundle(f'js/yadcf-{yadcf_ver}/jquery.dataTables.yadcf{yadcf_suffix}.js', filters='jsmin'),

        # # select2 is required for use by Editor forms
        Bundle(f'js/select2-{s2_ver}/js/select2.full.js', filters='jsmin'),
        # # the order here is important
        Bundle('js/FieldType-Select2/editor.select2-v4.js', filters='jsmin'),

        # # date time formatting for datatables editor, per https://editor.datatables.net/reference/field/datetime
        # Bundle('js/moment-{ver}/moment.js'.format(ver=moment_ver), filters='jsmin'),

        # # d3
        # Bundle('js/d3-{ver}/d3.js'.format(ver=d3_ver), filters='jsmin'),

        # # ckeditor (note this is already minimized, and filter through jsmin causes problems)
        # 'js/ckeditor5-build-{type}-{ver}/build/ckeditor.js'.format(ver=cke_ver, type=cke_type),

        Bundle('layout.js', filters='jsmin'),

        # must be before datatables
        Bundle('mutex-promise.js', filters='jsmin'),                     # from loutilities
        Bundle('editor-saeditor.js', filters='jsmin'),                   # from loutilities
        # Bundle('js/nunjucks-{ver}/nunjucks.js'.format(ver=nunjucks_ver), filters='jsmin'),
        # Bundle('admin/nunjucks/templates.js', filters='jsmin'),
        Bundle('editor.fieldType.display.js', filters='jsmin'),          # from loutilities
        Bundle('editor.ckeditor5.js', filters='jsmin'),                  # from loutilities
        Bundle('admin/beforedatatables.js', filters='jsmin'),
        Bundle('editor.googledoc.js', filters='jsmin'),                  # from loutilities
        Bundle('datatables.dataRender.googledoc.js', filters='jsmin'),   # from loutilities
        Bundle('user/admin/beforedatatables.js', filters='jsmin'),       # from loutilities
        Bundle('editor.select2.mymethods.js', filters='jsmin'),          # from loutilities
        Bundle('editor.displayController.onPage.js', filters='jsmin'),   # from loutilities
        Bundle('datatables-childrow.js', filters='jsmin'),               # from loutilities

        Bundle('datatables.js', filters='jsmin'),                        # from loutilities

        # must be after datatables.js
        Bundle('datatables.dataRender.ellipsis.js', filters='jsmin'),    # from loutilities
        Bundle('datatables.dataRender.datetime.js', filters='jsmin'),    # from loutilities
        Bundle('editor.buttons.editrefresh.js', filters='jsmin'),        # from loutilities
        Bundle('editor.buttons.editchildrowrefresh.js', filters='jsmin'),  # from loutilities
        Bundle('editor.buttons.separator.js', filters='jsmin'),          # from loutilities
        Bundle('filters.js', filters='jsmin'),                           # from loutilities
        Bundle('utils.js', filters='jsmin'),                             # from loutilities
        Bundle('user/admin/groups.js', filters='jsmin'),                 # from loutilities

        # # Bundle('admin/editor.buttons.invites.js', filters='jsmin'),
        # Bundle('admin/afterdatatables.js', filters='jsmin'),

        output='gen/admin.js',
        ),

    'admin_css': Bundle(
        Bundle(f'js/jquery-ui-{jq_ui_ver}.custom/jquery-ui.css', filters=['cssrewrite', 'cssmin']),
        Bundle(f'js/jquery-ui-{jq_ui_ver}.custom/jquery-ui.structure.css', filters=['cssrewrite', 'cssmin']),
        Bundle(f'js/jquery-ui-{jq_ui_ver}.custom/jquery-ui.theme.css', filters=['cssrewrite', 'cssmin']),
        Bundle(f'js/DataTables-{dt_datatables_ver}/datatables.css', filters=['cssrewrite', 'cssmin']),
        
        Bundle(f'js/smartmenus-{sm_ver}/css/sm-core-css.css', filters=['cssrewrite', 'cssmin']),
        Bundle(f'js/smartmenus-{sm_ver}/css/sm-blue/sm-blue.css', filters=['cssrewrite', 'cssmin']),

        Bundle(f'js/select2-{s2_ver}/css/select2.css', filters=['cssrewrite', 'cssmin']),
        Bundle('js/yadcf-{ver}/jquery.dataTables.yadcf.css'.format(ver=yadcf_ver), filters=['cssrewrite', 'cssmin']),

        Bundle(f'js/fontawesome-{fa_ver}/css/fontawesome.css', filters=['cssrewrite', 'cssmin']),
        Bundle(f'js/fontawesome-{fa_ver}/css/solid.css', filters=['cssrewrite', 'cssmin']),
        Bundle(f'js/fontawesome-{fa_ver}/css/regular.css', filters=['cssrewrite', 'cssmin']),

        Bundle('datatables.css', filters=['cssrewrite', 'cssmin']),   # from loutilities
        Bundle('editor.css', filters=['cssrewrite', 'cssmin']),       # from loutilities
        Bundle('filters.css', filters=['cssrewrite', 'cssmin']),      # from loutilities
        Bundle('branding.css', filters=['cssrewrite', 'cssmin']),     # from loutilities

        Bundle('style.css', filters=['cssrewrite', 'cssmin']),
        Bundle('admin/style.css', filters=['cssrewrite', 'cssmin']),

        output='gen/admin.css',
        # cssrewrite helps find image files when ASSETS_DEBUG = False
        # filters=['cssrewrite', 'cssmin'],
        ),
    
    'assets_js': Bundle(
        'admin_js'
    ),
    
    'assets_css': Bundle(
        'admin_css'
    )
}

asset_env = Environment()