# Funnl is an open-source one-file WSGI framework.
# http://github.com/joshmarshall/funnl
#
# Copyright 2010 Josh Marshall
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
FUNNL
=====
Here's a simple usage example:
-----------------------
from funnl import Handler, Server

class Page(Handler):
    route = r'/page_id/(a-z0-9_\-)+'
    
    def get(self, page_id):
        return self.render('page.htm', page_id=page_id)
        
server = Server()
server.add_handler(Page)
server.serve(port=8080)
--------------------------
You should also be able to pass "server" into any server / middleware 
that expects a WSGI-compatbile application. Just like any normal WSGI
application, you can return arbitrary text or even a generator if 
necessary (for example, if you are reading from a file. The StaticHandler
does this.)

By default the "render" and "render_list" method look for a "views" 
sub-folder in your current directory, but you can easily overwrite this
using the view_path server configuration option:

server = Server(view_path='/var/www/views')

Serving static files is easy. To use a "static" sub-folder in your
current directory, all you have to do is run:

server.enable_static()

Your files will be available under the /static path. For example, the
URL to a  file in your static folder that is at the location 
"images/favicon.ico" would be:

http://HOST:PORT/static/images/favicon.ico

If you want to serve static files in another directory or with a
different URL, just pass one or both parameters to Server:

server = Server(
    static_path='/var/www/static', 
    static_url=r'/files/(.+)'
)
server.enable_static()
"""

import re
import sys
import os
import socket
import string
import mimetypes
import logging
import wsgiref.util
try:
    from urlparse import parse_qs
except ImportError:
    # Python <= 2.5
    from cgi import parse_qs
    
try:
    import json
except ImportError:
    import simplejson as json
from wsgiref.simple_server import make_server, WSGIRequestHandler
from wsgiref.simple_server import WSGIServer
from SocketServer import ThreadingMixIn
import traceback

HTTP_CODES = {
    200: "OK",
    302: "Redirect",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    500: "Server error"
}

ROOT_PATH = os.path.abspath('./')
VIEW_PATH = os.path.join(ROOT_PATH, "views")
STATIC_PATH = os.path.join(ROOT_PATH, "static")
STATIC_URL = r"/static/(.+)"
TEMPLATE_CACHE = {}

class FunnlServer(ThreadingMixIn, WSGIServer):
    pass

class WSGIQuietHandler(WSGIRequestHandler):
    
    def log_message(self, *args, **kwargs):
        return

class Handler(object):
    route = r"/"
    
    def __init__(self, path, environ, start_response, params, **kwargs):
        self.headers = {
            "content-type": "text/html"
        }
        self.environment = environ
        self.start_response = start_response
        self.path = path
        self.params = params
        self.arguments = kwargs
        self.status = 200
        
    def error(self, code, message=None):
        self.status = code
        self.headers["content-type"] = "text/plain"
        response = ""
        if message:
            response = message
        return response
        
    def redirect(self, url):
        self.status = 302
        self.headers["location"] = url
        return ""
        
    def render(self, view, **kwargs):
        template = string.Template(self._get_view(view))
        return template.substitute(**kwargs)
        
    def _get_view(self, view):
        if not TEMPLATE_CACHE.has_key(view):
            view_path = os.path.join(self.params.get('view_path'), view)
            TEMPLATE_CACHE[view] = open(view_path, "r").read()
        return TEMPLATE_CACHE[view]
        
    def render_list(self, view, items):
        template = self._get_view(view)
        parts = []
        for item in items:
            parts.append(string.Template(template).substitute(**item))
        return ''.join(parts)
        
    def get_argument(self, arg, *args, **kwargs):
        value = self.arguments.get(arg)
        if value and len(value) > 0:
            return value[0]
        if kwargs.has_key("default"):
            return kwargs.get("default")
        elif len(args) > 0:
            return args[0]
        raise ValueError("No argument %s" % arg)      
        
class ErrorHandler(Handler):
    
    code = 500
    
    @classmethod
    def new(cls, code):
        class ErrorResponse(cls):
            pass
        ErrorResponse.code = code
        return ErrorResponse
    
    def get(self, message=None):
        return self.error(self.code, message)
    
    def post(self):
        return self.error(self.code, message)
    
    def head(self):
        return self.error(self.code)
        
    def put(self):
        return self.error(self.code, message)
        
class StaticHandler(Handler):
    
    route = STATIC_URL
    static_path = STATIC_PATH
    
    @classmethod
    def new(cls, path, route):
        class StaticHandlerSubClass(StaticHandler):
            pass
        StaticHandlerSubClass.route = route
        StaticHandlerSubClass.static_path = path
        return StaticHandlerSubClass
    
    def get(self, sub_path):
        path_parts = [p.strip() for p in sub_path.split("/") if p.split()]
        path = self.static_path
        for part in path_parts:
            path = os.path.join(path, part)
            if not os.path.exists(path):
                return self.error(404)
        if not os.path.isfile(path) or not os.access(path, os.R_OK):
            return self.error(403, "Access is forbidden.")
        size = os.stat(path).st_size
        mimetype = mimetypes.guess_type(path)[0]
        if not mimetype:
            mimetype = 'application/octet-stream'
        self.headers['content-type'] = mimetype
        self.headers['content-length'] = size
        return self.send_file(path)

    def send_file(self, path):
        wrapper = wsgiref.util.FileWrapper(open(path, "rb"))
        try:
            for chunk in wrapper:
                yield chunk
        finally:
            wrapper.close()

class Server(object):
    
    def __init__(self, **params):
        self.handlers = []
        params.setdefault('view_path', VIEW_PATH)
        params.setdefault('static_path', STATIC_PATH)
        params.setdefault('static_url', STATIC_URL)
        self.params = params
        
    def serve(self, port, address=None, quiet=False):
        if not address:
            address = ""
        handler = WSGIRequestHandler
        if quiet:
            handler = WSGIQuietHandler
        server = make_server(
            address, port, self.app, 
            server_class=FunnlServer,
            handler_class=handler
        )
        if not address:
            address = socket.gethostname()
        if not quiet:
            print "Serving on http://%s:%s" % (address, port)
            print "(Type Ctrl-C to stop)" 
        server.serve_forever()
        
    def enable_static(self, path=None, route=None):
        if not path:
            path = self.params.get('static_path')
        if not route:
            route = self.params.get('static_url')
        self.add_handler(StaticHandler.new(path, route))    
    
    def add_handler(self, handler):
        self.handlers.append(handler)
        
    def add_handlers(self, *args):
        for handler in args:
            self.add_handler(handler)
    
    def app(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        method_name = environ.get("REQUEST_METHOD", "GET").lower()
        queries = parse_qs(environ.get("QUERY_STRING", ""))
        args = ()
        use_handler = None
        for handler_class in self.handlers:
            match = re.match(handler_class.route, path)
            if match and len(match.group()) == len(path):
                use_handler = handler_class
                args = match.groups()
                break
        if not use_handler or not hasattr(use_handler, method_name):
            use_handler = ErrorHandler.new(404)
        handler = use_handler(
            path, environ, start_response, 
            self.params, **queries
        )
        method = getattr(handler, method_name)
        exception = None
        result = None
        try:
            result = method(*args)
        except Exception:
            exception = sys.exc_info()
        if type(result) is dict:
            try:
                result = [json.dumps(result),]
            except TypeError:
                exception = sys.exc_info()
            else:
                handler.headers["content-type"] = "application/json"
        if exception:
            error = ''.join(traceback.format_exception(*exception))
            logging.error(error)
            result = handler.error(500, error)
        if type(result) in (str, unicode):
            # auto wrapping of strings
            result = [result,]
        status_code = handler.status
        status = "%s %s" % (status_code, HTTP_CODES.get(status_code))
        headers = [
            (key, '%s' % value) for
            key, value in handler.headers.iteritems()
        ]
        start_response(status, headers)
        return result
        
    __call__ = app
