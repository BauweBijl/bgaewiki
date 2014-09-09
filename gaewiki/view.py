# encoding=utf-8

import logging
import os

from django.utils import simplejson
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

import access
import model
import settings
import util


DEFAULT_LABEL_BODY = u"""name: %(title)s
---
# %(title)s

<p class="alert alert-info">Pages in this category:</p>

[[List:%(label)s]]

_<p class="alert alert-info">This is an automatically generated page.</p>_
"""


def render(template_name, data):
    filename = os.path.join(os.path.dirname(__file__), 'templates', template_name)
    if not os.path.exists(filename):
        raise Exception('Template %s not found.' % template_name)
    if 'user' not in data:
        data['user'] = model.WikiUser.get_or_create(users.get_current_user())
    if data['user']:
        data['log_out_url'] = users.create_logout_url(os.environ['PATH_INFO'])
    else:
        data['log_in_url'] = users.create_login_url(os.environ['PATH_INFO'])
    if 'is_admin' not in data:
        data['is_admin'] = users.is_current_user_admin()
    if 'sidebar' not in data:
        data['sidebar'] = get_sidebar()
    if 'footer' not in data:
        data['footer'] = get_footer()
    if 'settings' not in data:
        data['settings'] = settings.get_all()
    if 'base' not in data:
        data['base'] = util.get_base_url()
    return template.render(filename, data)


def get_sidebar():
    page_name = settings.get('sidebar', 'gaewiki:sidebar')
    page = model.WikiContent.get_by_title(page_name)
    if page.is_saved():
        body = page.body
    else:
        body = u'\n\n<h4>This sidebar is used as menu, place your wiki links inside a list with these html tags:</h4>\n\n<code><\\ul class="nav"><\li></code>\n\n<code>[&#173;[SAMPLE_LINK_TO_PAGE]]</code>\n\n<code><\/li><\/ul></code>\n\n[<ul class="nav"><li>Edit the menu</li></ul>](/w/edit?page=%s)' % page_name
    return body


def get_footer():
    page_name = settings.get('footer', 'gaewiki:footer')
    page = model.WikiContent.get_by_title(page_name)
    if page.is_saved():
        body = page.body
    else:
        body = u'[BGAEWiki](https://github.com/BauweBijl/bgaewiki) by [Bauwe Bijl](http://www.bauwe.nl)'
    return body


def view_page(page, user=None, is_admin=False, revision=None):
    page = page.get_redirected()

    if page.title.startswith("Label:") and not page.body:
        page.body = DEFAULT_LABEL_BODY % {"title": page.title, "label": page.title[6:]}

    data = {
        'page': page,
        'is_admin': is_admin,
        'is_plain': page.get_property('format') == 'plain',
        'can_edit': access.can_edit_page(page.title, user, is_admin),
        'page_labels': page.get_property('labels', []),
        'revision': revision,
    }

    # logging.debug(data)

    if settings.get('enable-map'):
        if page.get_property('map_label'):
            data['map_url'] = '/w/pages/map?label=' + util.uurlencode(page.get_property('map_label'))
        elif data['can_edit'] or page.geopt:
            data['map_url'] = '/w/map?page=' + util.uurlencode(page.title)

    if revision:
        logging.debug(u'Viewing page "%s" (revision %s)' % (data['page'].title, revision))
    else:
        logging.debug(u'Viewing page "%s"' % data['page'].title)
    return render('view_page.html', data)


def edit_page(page):
    logging.debug(u'Editing page "%s"' % page.title)
    return render('edit_page.html', {
        'page': page,
    })


def list_pages(pages):
    logging.debug(u'Listing %u pages.' % len(pages))
    return render('index.html', {
        'pages': pages,
    })


def list_pages_feed(pages):
    logging.debug(u'Listing %u pages.' % len(pages))
    return render('index.rss', {
        'pages': pages,
    })


def show_page_history(page, user=None, is_admin=False):
    return render('history.html', {
        'page_title': page.title,
        'revisions': page.get_history(),
        'can_edit': access.can_edit_page(page.title, user, is_admin),
    })


def get_sitemap(pages):
    return render('sitemap.xml', {
        'pages': pages,
    })


def get_change_list(pages):
    return render('changes.html', {
        'pages': pages,
    })


def get_change_feed(pages):
    return render('changes.rss', {
        'pages': pages,
    })


def get_backlinks(page, links):
    return render('backlinks.html', {
        'page_title': page.title,
        'page_links': links,
    })


def get_users(users):
    return render('users.html', {
        'users': users,
    })


def get_import_form():
    return render('import.html', {})


def show_interwikis(iw):
    return render('interwiki.html', {
        'interwiki': iw,
    })


def show_profile(wiki_user):
    return render('profile.html', {
        'user': wiki_user,
    })


def show_page_map(label):
    """Renders the base page map code."""
    return render('page_map.html', {
        'map_label': label.replace('_', ' '),
    })


def show_single_page_map(page):
    """Renders a page that displays a page on the map."""
    pt = page.get_property('geo', default='61.72160269540121, 94.21821875')
    return render('single_page_map.html', {
        'page': page,
        'page_ll': pt.split(',')
    })


def show_pages_map_data(pages):
    """Returns the JavaScript with markers."""
    data = {
        'bounds': {
            'minlat': 999,
            'minlng': 999,
            'maxlat': 0,
            'maxlng': 0,
        },
        'markers': [],
        'length': len(pages),
    }

    for page in pages:
        lat = page.geopt.lat
        lng = page.geopt.lon
        if lat < data['bounds']['minlat']:
            data['bounds']['minlat'] = lat
        if lng < data['bounds']['minlng']:
            data['bounds']['minlng'] = lng
        if lat > data['bounds']['maxlat']:
            data['bounds']['maxlat'] = lat
        if lng > data['bounds']['maxlng']:
            data['bounds']['maxlng'] = lng

        data['markers'].append({
            'lat': lat,
            'lng': lng,
            'title': page.title,
            'html': render('map_info_window.html', {'page': page}).decode('utf-8'),
        })

    return 'var map_data = ' + simplejson.dumps(data) + ';'


def view_image_upload_page(user, is_admin, submit_url):
    data = {
        "user": user,
        "is_admin": is_admin,
        "submit_url": submit_url,
    }
    return render("upload_image.html", data)


def view_image(img, user, is_admin):
    data = {
        "image": img,
        "user": user,
        "is_admin": is_admin,
    }
    return render("view_image.html", data)


def view_image_list(lst, user, is_admin):
    data = {
        "images": lst,
        "user": user,
        "is_admin": is_admin,
    }
    return render("image_list.html", data)
