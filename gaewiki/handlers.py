# encoding=utf-8

import logging
import os
import traceback
import urllib

from django.utils import simplejson
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.api import users
from google.appengine.ext import blobstore
from google.appengine.ext import webapp
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.runtime.apiproxy_errors import OverQuotaError

import access
import images
import model
import settings
import util
import view


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class BadRequest(Exception):
    pass


class RequestHandler(webapp.RequestHandler):
    def reply(self, content, content_type='text/plain', status=200, save_as=None):
        self.response.headers['Content-Type'] = content_type + '; charset=utf-8'
        if save_as:
            self.response.headers['Content-Disposition'] = 'attachment; filename="%s"' % save_as
        self.response.out.write(content)

    def dump_request(self):
        for k in self.request.arguments():
            logging.debug('%s = %s' % (k, self.request.get(k)))

    def check_open_wiki(self):
        if not access.can_see_most_pages(users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden

    def show_error_page(self, status_code):
        defaults = {
            400: '<p class="alert alert-info">Bad request.</p>',
            403: '<p class="alert alert-warning">Access denied, try logging in.</p>',
            500: '<p class="alert alert-danger">Something bad happened.</p>',
        }
        page = model.WikiContent.get_error_page(status_code, defaults.get(status_code))
        self.reply(view.view_page(page, user=users.get_current_user(), is_admin=users.is_current_user_admin()), 'text/html')

    def handle_exception(self, e, debug_mode):
        if debug_mode or True:
            logging.error(e, exc_info=True)

        if self.is_ajax():
            self.reply(simplejson.dumps({
                "status": "error",
                "error": unicode(e),
                "error_class": e.__class__.__name__,
            }), "application/json")
        elif type(e) == BadRequest:
            self.show_error_page(400)
        elif type(e) == Forbidden:
            self.show_error_page(403)
        elif type(e) == NotFound:
            self.show_error_page(404)
        elif debug_mode:
            return webapp.RequestHandler.handle_exception(self, e, debug_mode)
        else:
            self.show_error_page(500)

    def redirect(self, url):
        if self.is_ajax():
            return self.reply(simplejson.dumps({
                "status": "redirect",
                "url": url,
            }))
        return super(RequestHandler, self).redirect(url)

    def is_ajax(self):
        return os.environ.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"

    def get_memcache(self):
        """memcache is active only anonymous user."""
        content = None
        user = users.get_current_user()
        if not user:
            content = memcache.get(self.get_memcache_key())
        if not content:
            content = self.get_content()
            if not user:
                memcache.set(self.get_memcache_key(), content)
        return content


class PageHandler(RequestHandler):
    def get(self, page_name):
        try:
            self.show_page(urllib.unquote(page_name).decode('utf-8'))
        except OverQuotaError, e:
            self.reply("Over quota.  Please try later.", status=502)

    def show_page(self, title):
        if title.startswith('w/'):
            raise Exception('No such page.')
        if not access.can_read_page(title, users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden
        self.title = title.replace('_', ' ')
        self.raw = self.request.get("format") == "raw"
        self.revision = self.request.get("r")

        if self.raw:
            body = self.get_memcache()
            content_type = str(body.get("content-type", "text/plain"))
            self.reply(body["text"], content_type=content_type)
        else:
            self.reply(self.get_memcache(), 'text/html')

    def get_memcache_key(self):
        if self.raw:
            return 'RawPage:' + self.title
        elif self.revision:
            return "PageRevision:" + self.revision
        else:
            return 'Page:' + self.title

    def get_content(self):
        page = model.WikiContent.get_by_title(self.title)
        if self.raw:
            return model.WikiContent.parse_body(page.body or '')
        else:
            if self.revision:
                revision = model.WikiRevision.get_by_key(self.request.get("r"))
                if revision is None:
                    raise NotFound("No such revision.")
                page.body = revision.revision_body
                page.author = revision.author
                page.updated = revision.created
            return view.view_page(page, user=users.get_current_user(), is_admin=users.is_current_user_admin(), revision=self.revision)


class StartPageHandler(PageHandler):
    def get(self):
        self.show_page(settings.get_start_page_name())


class EditHandler(RequestHandler):
    def get(self):
        title = self.request.get('page')
        if not title:
            raise BadRequest
        self.edit_page(title)

    def edit_page(self, title, body=None):
        page = model.WikiContent.get_by_title(title)
        if body:
            page.body = body
        user = users.get_current_user()
        is_admin = users.is_current_user_admin()
        if not access.can_edit_page(title, user, is_admin):
            raise Forbidden
        if not body and not page.is_saved():
            page.load_template(user, is_admin)
        self.reply(view.edit_page(page), 'text/html')

    def post(self):
        title = urllib.unquote(str(self.request.get('name'))).decode('utf-8')
        if self.request.get('Preview'):
            self.edit_page(title, self.request.get('body'))
            return

        user = users.get_current_user()
        if not access.can_edit_page(title, user, users.is_current_user_admin()):
            raise Forbidden
        page = model.WikiContent.get_by_title(title)
        page.update(body=self.request.get('body'), author=user, delete=self.request.get('delete'))
        self.redirect('/' + urllib.quote(page.title.encode('utf-8').replace(' ', '_')))
        taskqueue.add(url="/w/cache/purge", params={})


class CachePurgeHandler(webapp.RequestHandler):
    def get(self):
        if users.is_current_user_admin():
            taskqueue.add(url="/w/cache/purge", params={})

    def post(self):
        memcache.delete('Index:')
        memcache.delete('IndexFeed:')
        memcache.delete('Sitemap:')
        memcache.delete('Changes:')
        memcache.delete('ChangesFeed:')
        for page in model.WikiContent.all():
            memcache.delete('Page:' + page.title)
            memcache.delete('RawPage:' + page.title)
            memcache.delete('PageHistory:' + page.title)
            memcache.delete('BackLinks:' + page.title)
            for label in page.labels:
                memcache.delete('PagesFeed:' + label)
                memcache.delete('GeotaggedPagesFeed:' + label)
                memcache.delete('GeotaggedPagesJson:' + label)


class IndexHandler(RequestHandler):
    def get(self):
        self.check_open_wiki()
        self.reply(self.get_memcache(), 'text/html')

    def get_memcache_key(self):
        return 'Index:'

    def get_content(self):
        return view.list_pages(model.WikiContent.get_all())


class IndexFeedHandler(RequestHandler):
    def get(self):
        self.check_open_wiki()
        self.reply(self.get_memcache(), 'application/atom+xml')

    def get_memcache_key(self):
        return 'IndexFeed:'

    def get_content(self):
        return view.list_pages_feed(model.WikiContent.get_recently_added())


class PagesFeedHandler(RequestHandler):
    def get(self):
        self.check_open_wiki()
        self.label = self.request.get('label')
        self.reply(self.get_memcache(), 'application/atom+xml')

    def get_memcache_key(self):
        return 'PagesFeed:' + self.label

    def get_content(self):
        return view.list_pages_feed(model.WikiContent.get_recent_by_label(self.label))


class PageHistoryHandler(RequestHandler):
    def get(self):
        self.title = self.request.get('page')
        if not access.can_read_page(self.title, users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden
        self.reply(self.get_memcache(), 'text/html')

    def get_memcache_key(self):
        return 'PageHistory:' + self.title

    def get_content(self):
        page = model.WikiContent.get_by_title(self.title)
        return view.show_page_history(page, user=users.get_current_user(), is_admin=users.is_current_user_admin())


class RobotsHandler(RequestHandler):
    def get(self):
        content = "Sitemap: %s/sitemap.xml\n" % util.get_base_url()
        content += "User-agent: *\n"
        content += "Disallow: /gae-wiki-static/\n"
        content += "Disallow: /w/\n"
        self.reply(content, 'text/plain')


class SitemapHandler(RequestHandler):
    def get(self):
        self.check_open_wiki()
        self.reply(self.get_memcache(), 'text/xml')

    def get_memcache_key(self):
        return 'Sitemap:'

    def get_content(self):
        return view.get_sitemap(model.WikiContent.get_publicly_readable())


class ChangesHandler(RequestHandler):
    def get(self):
        if not access.can_see_most_pages(users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden
        self.reply(self.get_memcache(), 'text/html')

    def get_memcache_key(self):
        return 'Changes:'

    def get_content(self):
        return view.get_change_list(model.WikiContent.get_changes())


class ChangesFeedHandler(RequestHandler):
    def get(self):
        if not access.can_see_most_pages(users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden
        self.reply(self.get_memcache(), 'text/xml')

    def get_memcache_key(self):
        return 'ChangesFeed:'

    def get_content(self):
        return view.get_change_feed(model.WikiContent.get_changes())


class BackLinksHandler(RequestHandler):
    def get(self):
        self.title = self.request.get('page')
        if not access.can_read_page(self.title, users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden
        self.reply(self.get_memcache(), 'text/html')

    def get_memcache_key(self):
        return 'BackLinks:' + self.title

    def get_content(self):
        page = model.WikiContent.get_by_title(self.title)
        return view.get_backlinks(page, page.get_backlinks())


class UsersHandler(RequestHandler):
    def get(self):
        if not users.is_current_user_admin():
            raise Forbidden
        # self.check_open_wiki()
        self.reply(view.get_users(model.WikiUser.get_all()), 'text/html')


class DataExportHandler(RequestHandler):
    def get(self):
        if not users.is_current_user_admin():
            raise Forbidden
        pages = dict([(p.title, {
            'author': p.author and p.author.wiki_user.email(),
            'updated': p.updated.strftime('%Y-%m-%d %H:%M:%S'),
            'body': p.body,
        }) for p in model.WikiContent.get_all()])
        self.reply(simplejson.dumps(pages), 'application/json', save_as='gae-wiki.json')


class DataImportHandler(RequestHandler):
    def get(self):
        if not users.is_current_user_admin():
            raise Forbidden
        self.reply(view.get_import_form(), 'text/html')

    def post(self):
        if not users.is_current_user_admin():
            raise Forbidden
        merge = self.request.get('merge') != ''

        loaded = simplejson.loads(self.request.get('file'))
        for title, content in loaded.items():
            page = model.WikiContent.get_by_title(title)
            author = content['author'] and users.User(content['author'])
            page.update(content['body'], author, False)

        self.reply("Done.")


class InterwikiHandler(RequestHandler):
    def get(self):
        iw = settings.get_interwikis()
        self.reply(view.show_interwikis(iw), 'text/html')


class ProfileHandler(RequestHandler):
    """Implements personal profile pages."""
    def get(self):
        user = users.get_current_user()
        if user is None:
            raise Forbidden
        wiki_user = model.WikiUser.get_or_create(user)
        self.reply(view.show_profile(wiki_user), 'text/html')

    def post(self):
        user = users.get_current_user()
        if user is None:
            raise Forbidden
        wiki_user = model.WikiUser.get_or_create(user)
        wiki_user.nickname = self.request.get('nickname')
        wiki_user.public_email = self.request.get('email')
        wiki_user.put()
        self.redirect('/w/profile')


class GeotaggedPagesFeedHandler(RequestHandler):
    """Returns data for the /w/pages/geotagged.rss feed.  Supports the 'label'
    argument."""
    def get(self):
        self.check_open_wiki()
        self.label = self.request.get('label', None)
        self.reply(self.get_memcache(), 'application/atom+xml')

    def get_memcache_key(self):
        return 'GeotaggedPagesFeed:' + self.label

    def get_content(self):
        return view.list_pages_feed(model.WikiContent.find_geotagged(label=self.label))


class GeotaggedPagesJsonHandler(RequestHandler):
    def get(self):
        self.check_open_wiki()
        self.label = self.request.get('label', None)
        self.reply(self.get_memcache(), 'text/javascript')

    def get_memcache_key(self):
        return 'GeotaggedPagesJson:' + self.label

    def get_content(self):
        return view.show_pages_map_data(model.WikiContent.find_geotagged(label=self.label))


class PageMapHandler(RequestHandler):
    """Returns a page that displays a Google Map."""
    def get(self):
        self.reply(view.show_page_map(self.request.get('label', None)), 'text/html')


class MapHandler(RequestHandler):
    """Shows a page on the map and allows editors move the pointer."""
    def get(self):
        page_name = self.request.get('page')
        if not page_name:
            raise NotFound('Page not found.')

        page = model.WikiContent.get_by_title(page_name)
        if page is None:
            raise NotFound('Page not found.')

        self.reply(view.show_single_page_map(page), 'text/html')

    def post(self):
        """Processes requests to move the pointer.  Expects arguments
        'page_name' and 'll'."""
        page = model.WikiContent.get_by_title(self.request.get('page_name'))
        if page is None:
            raise NotFound('Page not found.')
        if access.can_edit_page(page.title, users.get_current_user(), users.is_current_user_admin()):
            geo = self.request.get('lat') + ',' + self.request.get('lng')
            page.set_property('geo', geo)
            page.put()
        response = [l.strip() for l in page.get_property('geo').split(',')]
        self.reply(simplejson.dumps(response), 'application/json')


class LoginHandler(RequestHandler):
    def get(self):
        self.redirect(users.create_login_url('/'))


class ImageUploadHandler(RequestHandler, blobstore_handlers.BlobstoreUploadHandler):
    def get(self):
        user = users.get_current_user()
        is_admin = users.is_current_user_admin()
        if not access.can_upload_image(user, is_admin):
            raise Forbidden

        submit_url = blobstore.create_upload_url(self.request.path)

        html = view.view_image_upload_page(user, is_admin, submit_url)
        self.reply(html, "text/html")

    def post(self):
        if not access.can_upload_image(users.get_current_user(), users.is_current_user_admin()):
            raise Forbidden
        # After the file is uploaded, grab the blob key and return the image URL.
        upload_files = self.get_uploads('file')  # 'file' is file upload field in the form
        blob_info = upload_files[0]

        image_page_url = "/w/image/view?key=" + str(blob_info.key())
        return self.redirect(image_page_url)


class ImageServeHandler(RequestHandler):
    def get(self):
        img = images.Image.get_by_key(self.request.get("key"))

        data = {
            "meta": img.get_info(),
            "versions": [
                ("thumbnail", img.get_url(75, True), img.get_code(75, True)),
                ("small", img.get_url(200, False), img.get_code(200, False)),
                ("medium", img.get_url(500, False), img.get_code(500, False)),
            ]
        }

        page_title = "Image:" + img.get_key()
        data["pages"] = model.WikiContent.find_backlinks_for(page_title)

        html = view.view_image(data, user=users.get_current_user(),
            is_admin=users.is_current_user_admin())
        self.reply(html, 'text/html')


class ImageListHandler(RequestHandler):
    def get(self):
        lst = images.Image.find_all()
        html = view.view_image_list(lst, users.get_current_user(),
            users.is_current_user_admin())
        self.reply(html, "text/html")


handlers = [
    ('/', StartPageHandler),
    ('/robots\.txt$', RobotsHandler),
    ('/sitemap\.xml$', SitemapHandler),
    ('/w/backlinks$', BackLinksHandler),
    ('/w/changes$', ChangesHandler),
    ('/w/changes\.rss$', ChangesFeedHandler),
    ('/w/data/export$', DataExportHandler),
    ('/w/data/import$', DataImportHandler),
    ('/w/edit$', EditHandler),
    ('/w/history$', PageHistoryHandler),
    ('/w/image/upload', ImageUploadHandler),
    ('/w/image/view', ImageServeHandler),
    ('/w/image/list', ImageListHandler),
    ('/w/index$', IndexHandler),
    ('/w/index\.rss$', IndexFeedHandler),
    ('/w/interwiki$', InterwikiHandler),
    ('/w/map', MapHandler),
    ('/w/pages\.rss', PagesFeedHandler),
    ('/w/pages/geotagged\.rss', GeotaggedPagesFeedHandler),
    ('/w/pages/geotagged\.js', GeotaggedPagesJsonHandler),
    ('/w/pages/map', PageMapHandler),
    ('/w/profile', ProfileHandler),
    ('/w/users$', UsersHandler),
    ('/w/login', LoginHandler),
    ('/w/cache/purge$', CachePurgeHandler),
    ('/(.+)$', PageHandler),
]
