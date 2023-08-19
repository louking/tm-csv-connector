'''
nav - navigation
======================
define navigation bar based on privileges
'''

# standard

# pypi
from flask import g, current_app, url_for, request
from flask_nav3 import Nav
from flask_nav3.elements import Navbar, View, Subgroup, Link, Separator
from flask_nav3.renderers import SimpleRenderer
from dominate import tags
from flask_security import current_user
from slugify import slugify

# homegrown
from .version import __docversion__
from loutilities.user.roles import ROLE_SUPER_ADMIN

thisnav = Nav()

@thisnav.renderer()
class NavRenderer(SimpleRenderer):
    '''
    this generates nav_renderer renderer, referenced in the jinja2 code which builds the nav
    '''
    def visit_Subgroup(self, node):
        # 'a' tag required by smartmenus
        title = tags.a(node.title, href="#")
        group = tags.ul(_class='subgroup')

        if node.active:
            title.attributes['class'] = 'active'

        for item in node.items:
            group.add(tags.li(self.visit(item)))

        return [title, group]

@thisnav.navigation()
def nav_menu():
    navbar = Navbar('nav_menu')

    contexthelp = {}
    class add_view():
        def __init__(self, basehelp):
            self.basehelp = basehelp.format(docversion=__docversion__)

        def __call__(self, navmenu, text, endpoint, **kwargs):
            prelink = kwargs.pop('prelink', None)
            navmenu.items.append(View(text, endpoint, **kwargs))
            contexthelp[url_for(endpoint, **kwargs)] = self.basehelp + slugify(text + ' view')
            if not prelink:
                contexthelp[url_for(endpoint, **kwargs)] = self.basehelp + slugify(text + ' view')
            else:
                contexthelp[url_for(endpoint, **kwargs)] = self.basehelp + slugify(prelink + ' ' + text + ' view')

        def nomenu_help(self, text, endpoint, **kwargs):
            prelink = kwargs.pop('prelink', None)
            if not prelink:
                contexthelp[url_for(endpoint, **kwargs)] = self.basehelp + slugify(text + ' view')
            else:
                contexthelp[url_for(endpoint, **kwargs)] = self.basehelp + slugify(prelink + ' ' + text + ' view')


    connector_view = add_view('https://tmtility.readthedocs.io/en/{docversion}/tm-csv-connector-reference.html#')

    navbar.items.append(View('Home', 'public.home', interest=g.interest))
    navbar.items.append(View('Races', 'public.races', interest=g.interest))
    navbar.items.append(View('Results', 'public.results', interest=g.interest))
    navbar.items.append(View('Settings', 'public.settings', interest=g.interest))

    # common items
    if g.interest:
        pass
    # navbar.items.append(View('About', 'admin.sysinfo'))
    if request.path in contexthelp:
        navbar.items.append(Link('Help', contexthelp[request.path]))

    return navbar

thisnav.init_app(current_app)
