# encoding=utf-8

import cgi
import logging
import os
import re
import urllib

import markdown
import model
import settings
import images


cleanup_re_1 = re.compile('<h\d>.*', re.MULTILINE | re.DOTALL)


def parse_page(page_content):
    return model.WikiContent.parse_body(page_content)


def pageurl(title):
    return '/' + pageurl_rel(title)


def pageurl_rel(title):
    if type(title) == unicode:
        title = title.encode('utf-8')
    elif type(title) != str:
        title = str(title)
    return urllib.quote(title.replace(' ', '_'))


def wikify_filter(text, display_title=None, page_name=None):
    props = parse_page(text)
    text = parse_markdown(props['text'])

    if props.get("format") == "plain":
        return cgi.escape(props["text"])

    if display_title is None and 'display_title' in props:
        display_title = props['display_title']

    if display_title is not None:
        new = u'<h1>%s</h1>' % cgi.escape(display_title)
        if not display_title.strip():
            new = ''
        text = re.sub('<h1>(.+)</h1>', new, text)
    return wikify(text, title=page_name)


def parse_markdown(text):
    return markdown.markdown(text, settings.get('markdown-extensions', [])).strip()


WIKI_WORD_PATTERN = re.compile("\[\[(.+?)\]\]")


def wikify(text, title=None):
    text, count = WIKI_WORD_PATTERN.subn(lambda x: wikify_one(x, title), text)
    text = re.sub(r'\.  ', '.&nbsp; ', text)
    text = re.sub(u' +(—|--) +', u'&nbsp;— ', text)
    return text


def wikify_one(pat, real_page_title):
    """Wikifies one link."""
    page_name = page_title = pat.group(1)
    if "|" in page_name:
        page_name, page_title = page_name.split("|", 1)

    # interwiki
    if ':' in page_name:
        parts = page_name.split(':', 1)
        if ' ' not in parts[0]:
            if page_name == page_title:
                page_title = parts[1]
            if parts[0] == 'List':
                return list_pages_by_label(parts[1])
            elif parts[0] == 'gaewiki':
                return process_special_token(parts[1], real_page_title)
            elif parts[0] == 'ListChildren':
                return list_pages_by_label('gaewiki:parent:' + (parts[1] or real_page_title))
            elif parts[0] == 'Image':
                return render_image(parts[1].split(";"), page_title)
            iwlink = settings.get(u'interwiki-' + parts[0])
            if iwlink:
                return '<a class="iw iw-%s" href="%s" target="_blank">%s</a>' % (parts[0], iwlink.replace('%s', urllib.quote(parts[1].encode('utf-8'))), page_title)

    page = model.WikiContent.get_by_title(page_name)

    page_class = "int"
    page_link = pageurl(page_name)
    page_hint = page_name
    page_text = page_title

    if page is None or not page.is_saved():
        page_class += " missing"
        page_hint += " (create)"
        page_link = "/w/edit?page=" + pageurl_rel(page_name)

    return '<a class="%(class)s" href="%(href)s" title="%(hint)s">%(text)s</a>' % {
        "class": page_class,
        "href": page_link,
        "hint": cgi.escape(page_hint),
        "text": cgi.escape(page_text),
    }


def render_image(args, title):
    key = args[0]
    size = None
    crop = False
    align = None

    if not title:
        title = 'Click to view image details'

    for arg in args[1:]:
        if arg.startswith("size="):
            size = int(arg[5:])
        elif arg == "crop":
            crop = True
        elif arg in ("left", "right"):
            align = arg

    img = images.Image.get_by_key(key)

    attrs = "src='%s' alt='%s'" % (img.get_url(size, crop),
        cgi.escape(img.get_filename()))
    if align is not None:
        attrs += " align='%s'" % align

    return "<a href='/w/image/view?key=%s' title='%s'><img %s/></a>" % (img.get_key(), title, attrs)


def list_pages_by_label(label):
    """Returns a formatted list of pages with the specified label."""
    keys = label.split(';')
    pages = model.WikiContent.get_by_label(keys[0])

    if 'sort=date,desc' in keys:
        pages.sort(key=lambda p: p.created, reverse=True)
    else:
        pages.sort(key=lambda p: p.title.lower())

    items = []
    for page in pages:
        page_name = page.redirect or page.title
        items.append(u'<li class="list-group-item"><a href="%(url)s" title="%(hint)s">%(title)s</a></li>' % {
            "url": pageurl(page_name),
            "hint": cgi.escape(page_name),
            "title": page.get_property('display_title', page.title),
        })

    if not items:
        return ""

    return u'<ul class="list-group">%s</ul>' % u''.join(items)


def process_special_token(text, page_name):
    """Renders special code snippets such as an MP3 player."""
    parts = text.split(';')
    logging.debug(u'Parsing a special token: %s' % parts)

    if parts[0] == 'mp3player':
        url = None
        for part in parts:
            if part.startswith('url='):
                url = part[4:]
        if url is None and page_name is not None:
            page = model.WikiContent.get_by_title(page_name)
            if page is not None:
                url = page.get_property('file')
        if url is None:
            return '<!-- player error: no file -->'
        file_url = cgi.escape(url)
        return '<div class="player mp3player"><object type="application/x-shockwave-flash" data="/gae-wiki-static/player.swf" width="200" height="20"><param name="movie" value="/files/player.swf"/><param name="bgcolor" value="#eeeeee"/><param name="FlashVars" value="mp3=%s&amp;buttoncolor=000000&amp;slidercolor=000000&amp;loadingcolor=808080"/></object> <a href="%s">Download audio file</a></div>' % (file_url, file_url)

    elif parts[0] == 'map':
        return render_map(parts[1:], page_name)

    return u'<!-- unsupported token: %s -->' % parts[0]


def render_map(args, page_name):
    params = {
        'width': 300,
        'height': 200,
        'url': '/w/map?page=' + uurlencode(page_name),
        'class': 'map right',
    }

    for k, v in [a.split('=', 1) for a in args if '=' if a]:
        if k == 'page':
            params['url'] = '/w/map?page=' + uurlencode(v)
        elif k == 'label':
            params['url'] = '/w/pages/map?label=' + uurlencode(v)
        else:
            params[k] = v

    html = '<iframe class="%(class)s" width="%(width)s" height="%(height)s" src="%(url)s"></iframe>' % params
    return html


def pack_page_header(headers):
    """Builds a text page header from a dictionary."""
    lines = []
    for k, v in sorted(headers.items(), key=lambda x: x[0]):
        if k != 'text' and v is not None:
            if type(v) == list:
                v = u', '.join(v)
            lines.append(k + u': ' + v)
    return u'\n'.join(lines)


def uurlencode(value):
    if type(value) == unicode:
        value = value.encode('utf-8')
    try:
        if type(value) != str:
            raise Exception('got \"%s\" instead of a string.' % value.__class__.__name__)
        return urllib.quote(value.replace(' ', '_'))
    except Exception, e:
        return ''


def get_label_url(value):
    """Returns a URL to the label page.  Supports redirects."""
    if type(value) == str:
        value = value.decode('utf-8')
    value = u'Label:' + value

    page = model.WikiContent.get_by_title(value)
    if page.is_saved() and page.redirect:
        value = page.redirect

    return '/' + urllib.quote(value.replace(' ', '_').encode('utf-8'))


def get_base_url():
    url = 'http://' + os.environ['HTTP_HOST']
    if url.endswith(':80'):
        url = url[:-3]
    return url


def cleanup_summary(text):
    text = re.sub('<iframe.*</iframe>', '', text)
    text = cleanup_re_1.sub('', text)
    logging.debug(text)
    return text


def extract_links(text):
    if text is None:
        return []

    links = []

    for link in re.findall(WIKI_WORD_PATTERN, text):
        if "|" in link:
            link = link.split("|", 1)[0]

        if link.startswith("Image:"):
            link = link.split(";")[0]

        if link not in links:
            links.append(link)

    return links
