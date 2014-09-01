# encoding=utf-8

import os
import sys
import wsgiref.handlers


from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

import handlers


application = webapp.WSGIApplication(handlers.handlers)


sys.path.insert(0, os.path.dirname(__file__))
template.register_template_library('templatetags.filters')