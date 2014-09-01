# encoding=utf-8

import unittest

from google.appengine.api import users
from google.appengine.ext import testbed

import access
import model
import settings
import util

try:
    import view
    TEST_VIEWS = True
except:
    TEST_VIEWS = False


class TestCase(unittest.TestCase):
    """Base class for all tests, initializes the datastore testbed (in-memory
    storage)."""
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()
        settings.settings = None

    def tearDown(self):
        self.testbed.deactivate()

    def test_page_packing(self):
        """Tests whether page haders can be built correctly."""
        header = util.pack_page_header({
            'simple': 'foo',
            'list': ['foo', 'bar'],
            'text': 'must be ignored',
        })
        self.assertEquals('list: foo, bar\nsimple: foo', header)

    def test_page_parser(self):
        """Makes sure we can parse pages correctly."""
        args = util.parse_page('key: value\nkeys: one, two\n#ignore: me\n---\nhello, world.')
        self.assertEquals(3, len(args))
        self.assertEquals(args.get('key'), 'value')
        self.assertEquals(args.get('keys'), ['one', 'two'])
        self.assertEquals(args.get('text'), 'hello, world.')

        # windows line endings
        args = util.parse_page('key: value\nkeys: one, two\n#ignore: me\r\n---\r\nhello, world.')
        self.assertEquals(3, len(args))

        # old mac line endings
        args = util.parse_page('key: value\nkeys: one, two\n#ignore: me\r---\rhello, world.')
        self.assertEquals(3, len(args))

    def test_page_url(self):
        """Makes sure we can build correct page URLs."""
        self.assertEquals('/foo', util.pageurl('foo'))
        self.assertEquals('/foo_bar', util.pageurl('foo bar'))
        self.assertEquals('/foo%2C_bar%21', util.pageurl('foo, bar!'))
        self.assertEquals('/%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%BA%D0%B0', util.pageurl(u'проверка'))

    def test_wikify(self):
        checks = [
            ('foo bar', 'foo bar'),
            # Basic linking.
            ('[[foo bar]]', '<a class="int missing" href="/w/edit?page=foo_bar" title="foo bar (create)">foo bar</a>'),
            ('[[foo|bar]]', '<a class="int missing" href="/w/edit?page=foo" title="foo (create)">bar</a>'),
            # Interwiki linking.
            ('[[google:hello]]', u'<a class="iw iw-google" href="http://www.google.ru/search?q=hello" target="_blank">hello</a>'),
            ('[[missing:hello]]', '<a class="int missing" href="/w/edit?page=missing%3Ahello" title="missing:hello (create)">hello</a>'),
            # Multiple links on the same line.
            ('[[foo]], [[bar]]', '<a class="int missing" href="/w/edit?page=foo" title="foo (create)">foo</a>, <a class="int missing" href="/w/edit?page=bar" title="bar (create)">bar</a>'),
            # Check the typography features.
            ('foo. bar', 'foo. bar'),
            ('foo.  bar', 'foo.&nbsp; bar'),
            (u'foo  —  bar', u'foo&nbsp;— bar'),
            (u'foo  --  bar', u'foo&nbsp;— bar'),
        ]
        for got, wanted in checks:
            self.assertEquals(util.wikify(got), wanted)

    def test_page_creation(self):
        self.assertEquals(len(model.WikiContent.get_all()), 0)
        model.WikiContent(title='foo').put()
        self.assertEquals(len(model.WikiContent.get_all()), 1)

    def test_labelled_page_creation(self):
        self.assertEquals(len(model.WikiContent.get_all()), 0)

        page = model.WikiContent(title='foo')
        page.put()

        self.assertEquals(len(model.WikiContent.get_all()), 1)
        self.assertEquals(len(model.WikiContent.get_by_label('foo')), 0)

        page.body = 'labels: foo, bar\n---\n# foo'
        page.put()

        self.assertEquals(len(model.WikiContent.get_all()), 1)
        self.assertEquals(len(model.WikiContent.get_by_label('foo')), 1)

    def test_page_listing(self):
        self.assertEquals(util.wikify('[[List:foo]]'), '')
        model.WikiContent(title='bar', body='labels: foo\n---\n# bar\n\nHello, world.').put()
        model.WikiContent(title='baz', body='labels: foo\n---\n# baz\n\nHello, world.').put()
        self.assertEquals(util.wikify('[[List:foo]]'), u'<ul class="labellist"><li><a class="int" href="/bar" title="bar">bar</a></li><li><a class="int" href="/baz" title="baz">baz</a></li></ul>')

    def test_children_listing(self):
        self.assertEquals(len(model.WikiContent.get_all()), 0)

        model.WikiContent(title='foo/bar').put()
        model.WikiContent(title='foo/baz').put()
        self.assertEquals(len(model.WikiContent.get_all()), 2)

        self.assertEquals(util.wikify('[[ListChildren:foo]]'), u'<ul class="labellist"><li><a class="int" href="/foo/bar" title="foo/bar">foo/bar</a></li><li><a class="int" href="/foo/baz" title="foo/baz">foo/baz</a></li></ul>')
        self.assertEquals(util.wikify('[[ListChildren:]]', 'foo'), u'<ul class="labellist"><li><a class="int" href="/foo/bar" title="foo/bar">foo/bar</a></li><li><a class="int" href="/foo/baz" title="foo/baz">foo/baz</a></li></ul>')

    def test_settings_changing(self):
        self.assertEquals(settings.get('no-such-value'), None)
        settings.change({'no-such-value': 'yes'})
        self.assertEquals(settings.get('no-such-value'), 'yes')
        settings.change({'editors': 'one, two'})
        self.assertEquals(settings.get('editors'), ['one', 'two'])

    def test_uurlencode_filter(self):
        self.assertEquals(util.uurlencode(None), '')
        self.assertEquals(util.uurlencode('foo bar'), 'foo_bar')
        self.assertEquals(util.uurlencode(u'тест'), '%D1%82%D0%B5%D1%81%D1%82')

    def test_get_label_url(self):
        self.assertEquals(util.get_label_url('foo'), '/Label%3Afoo')
        self.assertEquals(util.get_label_url('foo bar'), '/Label%3Afoo_bar')
        self.assertEquals(util.get_label_url('foo, bar'), '/Label%3Afoo%2C_bar')
        self.assertEquals(util.get_label_url(u'тест'), '/Label%3A%D1%82%D0%B5%D1%81%D1%82')

    def test_markdown_extensions(self):
        self.assertEquals(util.parse_markdown('# foo'), '<h1>foo</h1>')

    def test_display_title(self):
        body = 'display_title: foo\n---\n# bar'
        text = util.wikify_filter(body)
        self.assertFalse('<h1>bar</h1>' in text)
        self.assertTrue('<h1>foo</h1>' in text)

        body = 'display_title:\n---\n# foo'
        text = util.wikify_filter(body)
        self.assertTrue('<h1>' not in text)

    def test_white_listing(self):
        self.assertEquals(False, access.is_page_whitelisted('Welcome'))
        settings.change({'page-whitelist': '^Wel.*'})
        self.assertEquals(True, access.is_page_whitelisted('Welcome'))

    def test_black_listing(self):
        self.assertEquals(False, access.is_page_blacklisted('Welcome'))
        settings.change({'page-blacklist': '^Wel.*'})
        self.assertEquals(True, access.is_page_blacklisted('Welcome'))
        settings.change({'page-whitelist': '.*come$'})
        self.assertEquals(False, access.is_page_blacklisted('Welcome'), 'White listing does not beat blacklisting.')

    def test_edit_system_pages(self):
        self.assertEquals(access.can_edit_page('gaewiki:settings', is_admin=True), True)
        self.assertEquals(access.can_edit_page('gaewiki:settings', is_admin=False), False)

    def test_open_editing(self):
        self.assertEquals(access.can_edit_page('foo'), False)
        settings.change({'open-editing': 'yes'})
        self.assertEquals(access.can_edit_page('foo'), True)
        settings.change({'page-blacklist': '^foo'})
        self.assertEquals(access.can_edit_page('foo'), False)

    def test_edit_orphan_page(self):
        settings.change({'open-editing': 'yes'})
        self.assertEquals(access.can_edit_page('foo/bar'), True)
        settings.change({'parents-must-exist': 'yes'})
        self.assertEquals(access.can_edit_page('foo/bar'), False)

    def test_editor_access(self):
        user = users.User('alice@example.com')
        self.assertEquals(access.can_edit_page('foo'), False)
        self.assertEquals(access.can_edit_page('foo', user), False)
        settings.change({'editors': user.email()})
        self.assertEquals(access.can_edit_page('foo', user), True)

    def test_admin_edits(self):
        settings.change({'open-editing': 'no', 'page-blacklist': '.*', 'parents-must-exist': 'yes'})
        self.assertEquals(access.can_edit_page('foo/bar'), False)
        self.assertEquals(access.can_edit_page('foo/bar', is_admin=True), True)

    def test_edit_locked_page(self):
        """Make sure that locked pages aren't editable."""
        model.WikiContent(title='foo', body='locked: yes\n---\n# foo').put()
        settings.change({'open-editing': 'yes', 'open-reading': 'yes'})
        self.assertEquals(access.can_edit_page('foo', is_admin=False), False)

    def test_list_changes_in_closed_wiki(self):
        settings.change({"open-reading": "yes", "open-writing": "yes"})
        self.assertTrue(isinstance(model.WikiContent.get_changes(), list))

        settings.change({"open-reading": "no", "open-writing": "no"})
        self.assertTrue(isinstance(model.WikiContent.get_changes(), list))

    def test_edit_page_with_local_editors(self):
        pass

    def test_page_reading(self):
        user = users.User('alice@example.com')

        # Unknown user, default access.
        settings.change({'open-reading': None, 'readers': None, 'editors': None})
        self.assertEquals(access.can_read_page('foo', user, False), True)

        # Unknown user, private wiki.
        settings.change({'open-reading': 'no'})
        self.assertEquals(access.can_read_page('foo', user, False), False)

        # A privilaged reader, private wiki.
        settings.change({'open-reading': 'no', 'readers': user.email(), 'editors': None})
        self.assertEquals(access.can_read_page('foo', user, False), True)

        # A privilaged editor, private wiki.
        settings.change({'open-reading': 'no', 'readers': None, 'editors': user.email()})
        self.assertEquals(access.can_read_page('foo', user, False), True)

        page = model.WikiContent(title='foo')

        # An unknown user, a private wiki and a public page.
        settings.change({'open-reading': 'no', 'readers': None, 'editors': None})
        page.body = 'public: yes\n---\n# foo'
        page.put()
        self.assertEquals(access.can_read_page('foo', user, False), True)

        # An unknown user, an open wiki and a private page.
        settings.change({'open-reading': 'yes', 'readers': None, 'editors': None})
        page.body = 'private: yes\n---\n# foo'
        page.put()
        self.assertEquals(access.can_read_page('foo', user, False), False)

        # An open wiki, a private page with explicit access to some regular user.
        settings.change({'open-reading': 'yes', 'readers': None, 'editors': None})
        page.body = 'private: yes\nreaders: %s\n---\n# foo' % user.email()
        page.put()
        self.assertEquals(access.can_read_page('foo', user, False), True)

    def test_access_to_special_pages(self):
        user = users.User('alice@example.com')

        settings.change({'open-reading': None, 'readers': None, 'editors': None})
        self.assertEquals(access.can_see_most_pages(user, False), True)

        settings.change({'open-reading': 'no', 'readers': None, 'editors': None})
        self.assertEquals(access.can_see_most_pages(user, False), False)

        settings.change({'open-reading': 'no', 'readers': user.email(), 'editors': None})
        self.assertEquals(access.can_see_most_pages(user, False), True)

        settings.change({'open-reading': 'no', 'readers': None, 'editors': user.email()})
        self.assertEquals(access.can_see_most_pages(user, False), True)

    def test_custom_nickname(self):
        u1 = users.User('alice@example.com')
        w1 = model.WikiUser.get_or_create(u1)
        self.assertEquals(w1.get_nickname(), 'alice')

        w1.nickname = 'bob'
        self.assertEquals(w1.get_nickname(), 'bob')

    def test_custom_public_email(self):
        u1 = users.User('alice@example.com')
        w1 = model.WikiUser.get_or_create(u1)
        self.assertEquals(w1.get_public_email(), 'alice@example.com')

        w1.public_email = 'bob@example.com'
        self.assertEquals(w1.get_public_email(), 'bob@example.com')

    def test_unique_nicknames(self):
        u1 = model.WikiUser.get_or_create(users.User('alice@example.com'))
        self.assertEquals(u1.get_nickname(), 'alice')

        u2 = model.WikiUser.get_or_create(users.User('alice@example.net'))
        nickname = u2.get_nickname()
        self.assertEquals(len(nickname), 9)
        self.assertTrue(nickname.startswith('alice'))
        self.assertTrue(nickname[-4:].isdigit())

    def test_underscores_in_titles(self):
        p1 = model.WikiContent(title='Hello World')
        p1.put()

        p2 = model.WikiContent.get_by_title('Hello_World')
        self.assertEquals(p1.key(), p2.key())

    def test_page_redirect(self):
        """Makes sure that redirects are supported when displaying pages."""
        if not TEST_VIEWS:
            return
        page1 = model.WikiContent(title='page1', body='redirect: page2\n---\n# page1')
        page1.put()

        page2 = model.WikiContent(title='page2', body='# page2')
        page2.put()

        html = view.view_page(page1)
        print html

    def test_logged_in_page_editing(self):
        alice = users.User('alice@example.com')

        settings.change({'open-editing': 'no'})
        self.assertFalse(access.can_edit_page("some page", user=None))
        self.assertFalse(access.can_edit_page("some page", user=alice))

        settings.change({'open-editing': 'yes'})
        self.assertTrue(access.can_edit_page("some page", user=None))
        self.assertTrue(access.can_edit_page("some page", user=alice))

        settings.change({'open-editing': 'login'})
        self.assertFalse(access.can_edit_page("some page", user=None))
        self.assertTrue(access.can_edit_page("some page", user=alice))

    def test_empty_links(self):
        text = util.parse_markdown("[]()")
        self.assertEquals(text, "<p>[]()</p>")

    def test_backlink_extraction(self):
        links = util.extract_links(None)
        self.assertEquals(links, [])

        text = "[[foo]], [[foo|bar]]"
        links = util.extract_links(text)
        self.assertEquals(links, ["foo"])

    def test_backlinks(self):
        page = model.WikiContent(title="test", body="[[foo]], [[bar]]")
        page.put()
        self.assertEquals(page.links, ["foo", "bar"])

        page2 = model.WikiContent(title="foo", body=None)
        self.assertEquals(page2.get_backlinks()[0].title, page.title)


def run_tests():
    suite = unittest.TestSuite()
    for method in dir(TestCase):
        if method.startswith('test_'):
            suite.addTest(TestCase(method))
    unittest.TextTestRunner().run(suite)


if __name__ == '__main__':
    run_tests()
