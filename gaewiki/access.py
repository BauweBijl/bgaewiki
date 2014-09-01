# encoding=utf-8

import re

import model
import settings
import util


def is_page_whitelisted(title):
    pattern = settings.get('page-whitelist')
    if pattern is None:
        return False
    return re.match(pattern, title) is not None


def is_page_blacklisted(title):
    if is_page_whitelisted(title):
        return False
    pattern = settings.get('page-blacklist')
    if pattern is None:
        return False
    return re.match(pattern, title) is not None


def can_edit_page(title, user=None, is_admin=False):
    if is_admin:
        return True

    if title.startswith('gaewiki:'):
        return False

    if '/' in title and settings.get('parents-must-exist') == 'yes':
        parent_title = '/'.join(title.split('/')[:-1])
        parent = model.WikiContent.gql('WHERE title = :1', parent_title).get()
        if parent is None:
            return False

    if settings.get('open-editing') == 'yes':
        if not model.WikiContent.get_by_title(title).is_locked():
            return not is_page_blacklisted(title)
    if user is None:
        return False
    if settings.get('open-editing') == 'login':
        return not is_page_blacklisted(title)
    if user.email() in settings.get('editors', []):
        return not is_page_blacklisted(title)
    return False


def can_read_page(title, user, is_admin):
    """Returns True if the user is allowed to read the specified page.

    Admins and global readers and editors are allowed to read all pages.  Other
    users are allowed to read all pages if the wiki is open or if the user is
    listed in the readers/editors page property.

    Otherwise no access."""
    if is_admin:
        return True

    is_user_reader = user and (user.email() in settings.get('readers', []) or user.email() in settings.get('editors', []))
    if is_user_reader:
        return True

    page = model.WikiContent.get_by_title(title)
    options = util.parse_page(page.body or '')

    is_open_wiki = settings.get('open-reading', 'yes') == 'yes'
    if is_open_wiki:
        if options.get('private') != 'yes':
            return True
        return user and (user.email() in options.get('readers', []) or user.email() in options.get('editors', []))
    elif settings.get('open-reading') == 'login':
        return options.get('public') == 'yes' or user
    else:
        return options.get('public') == 'yes'


def can_see_most_pages(user, is_admin):
    if is_admin:
        return True
    if settings.get('open-reading', 'yes') == 'yes':
        return True
    if user is None:
        return False
    if settings.get('open-reading') == 'login':
        return True
    if user.email() in settings.get('readers', []):
        return True
    if user.email() in settings.get('editors', []):
        return True
    return False


def can_upload_image(user=None, is_admin=False):
    if is_admin:
        return True

    if settings.get('image-uploading') == 'yes':
        return True
    if user and settings.get('image-uploading') == 'login':
        return True
    return False
