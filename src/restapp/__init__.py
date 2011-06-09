import os
import logging
import traceback

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from django.utils import simplejson as json

import context
import errors
import _handlers

class Endpoint(object):
    """Base class for REST endpoints. All endpoint should derive from this class and optionally
    implement one of the handler methods:
        get - called when a GET is sent to the '/root_url/id' endpoint
        post - called when a POST is sent to the '/root_url' endpoint
        query - called when a GET is sent to the '/root_url' endpoint
        upload - called when a POST is sent to the URL returned by ctx.upload_url()
    """

    # implementors must set this to the root url of the endpoint
    root_url = None

    def query(self, ctx):
        """Handler for GET requests. This handler should perform a query using any
        query parameters in the context
        Args:
            ctx - Request context.
        Returns:
            An list of objects that will later be formatted using one of the 'alt_query_Xxx' methods.
        """
        raise NotImplementedError()
    
    def get(self, ctx):
        """Handler for a GET request for a single resource. The handler return
        Args:
            ctx - request context
        Returns:
            An object that will later be formatted using one of the 'alt' methods.
            This could also be a tuple, in which case the first one should be a dictionary 
            or any other type serializable to JSON and the second one can be any type
            which will be passed to the alt_Xxx methods.
        """
        raise NotImplementedError()
    
    def post(self, ctx):
        """Handler for POST requests. POST request should create a new resource
        using data from the POST fields in the context.
        Args:
            ctx - request context
        Returns:
            A string that contains the key for the new created resource.
            This string will be used to redirect the user to the newly created resource
        """
        raise NotImplementedError()
    
    def upload(self, ctx):
        """Handler for POST requests sent implicitly via the App Engine upload service.
        In order to allow a client to upload a blob to this endpoint, call the ctx.upload_url() method
        to retrieve an upload URL. This URL should be used by the client to send an HTTP POST FORM.
        This method will be called by the App Engine blob upload service once the blob has been stored
        in the blobstore.
        Args:
            ctx - The request context. Use ctx.
        """
        raise NotImplementedError()
    
    def authenticate_request(self, ctx):
        """Called to authenticate a request. By default, does nothing.
        Args:
            ctx - The request context
        Returns:
            The authentication context which will be incorporated into the context.
        """
        return None

    def alt_json(self, ctx, obj):
        """Emits a JSON representation of the response dictionary into the response object
        Args:
            ctx - The request context
            obj - The object or tuple returned by a GET handler (if tuple, the first item is taken)
        """
        if isinstance(obj, tuple):
            obj = obj[0]

        ctx.response.headers['Content-Type'] = "application/json"
        ctx.response.out.write(json.dumps(obj, indent=4, sort_keys=True))

    def alt_jsonp(self, ctx, obj):
        """Emits a JSONP representation of the response dictionary
        Args:
            ctx - The request context
            obj - The object or tuple returned by a GET handler"""
            
        # make sure we have a 'callback' argument in the request
        callback_name = ctx.require('callback')
        if isinstance(obj, tuple):
            obj = obj[0]

        ctx.response.headers['Content-Type'] = "application/javascript"
        output = '%s(%s)' % (callback_name, json.dumps(obj, indent=4, sort_keys=True))
        ctx.response.out.write(output)

    def alt_query_html(self, ctx, list):
        """Creates an HTML representation for a query GET operation
        Args:
            ctx - The request context
            list - The array returned from the query method
        """
        self._alt_html(ctx, { 'results': list }, filename_prefix = 'query_')
    
    def alt_query_json(self, ctx, list):
        """Creates a JSON representation of a query GET operation
        Args:
            ctx - The request context.
            list - The list of objects returned from the query method
        """
        self.alt_json(ctx, list)
    
    def alt_query_jsonp(self, ctx, list):
        """Creates a JSONP representation of a query GET operation
        Args:
            ctx - The request context.
            list - The list of objects returned from the query method
        """
        self.alt_jsonp(ctx, list)
    
    def alt_html(self, ctx, obj):
        """Creates an HTML representation of a response object.
        This is done by looking for a template .html file and passing it the response object
        Args:
            ctx - The request context
            obj - The object or tuple returned by a GET handler (if tuple, only the first item is taken)
        """
        if isinstance(obj, tuple):
            obj = obj[0]
            
        self._alt_html(ctx, obj, filename_prefix = '')

    def write_html_template(self, ctx, file_name, template_dict):
        """Writes a templated html to the output stream.
        Args:
            ctx - The request context.
            file_name - The name of the file. The path will be determined by the directory of the endpoint module file.
            template_dict - A dictionary with template variables
        """
        path = os.path.join(os.path.dirname(ctx.endpoint_file), file_name)
        if not os.path.exists(path):
            ctx.response.set_status(404)
            ctx.response.out.write('unable to find file: %s' % path)
            return
        ctx.response.out.write(template.render(path, template_dict))
    
    def _alt_html(self, ctx, obj, filename_prefix = ''):
        name = ctx.endpoint_name.lower()
        if name.endswith('endpoint'): 
            name = name[:name.rfind('endpoint')]
        template_name = '%s%s.html' % (filename_prefix, name)
        self.write_html_template(ctx, template_name, obj)
    
    @classmethod
    def get_root_url(cls):
        """Returns the root_url of an endpoint""" 
        if not hasattr(cls, 'root_url') or cls.root_url == None or cls.root_url == '':
            raise Exception("'root_url' must be defined as an attribute of class " + cls.__name__)
        return cls.root_url
    
    @classmethod
    def construct_relative_url(cls, resource_path, alt = None):
        """Constructs a relative URL for a resource path and a representation.
        e.g. /events/1234?alt=json
        Args:
            resource_path - path to the resource within this endpoint (e.g. '1234' in the above example).
            alt - the alternative representation (e.g. 'json' in the above example).
        """
        root_url = cls.get_root_url()
            
        alt_postfix = ''
        if alt: alt_postfix = '?alt=' + alt
        return root_url + '/' + resource_path + alt_postfix
    
    @classmethod
    def construct_absolute_url(cls, ctx, resource_path, alt = None):
        rel = cls.construct_relative_url(resource_path, alt)
        return ctx.request.scheme + "://" + ctx.request.host + rel

    @classmethod
    def request_handler_class(cls):
        """Returns a request handler class for this endpoint"""
        class SpecificRequestHandler(_handlers.RequestHandler):
            def __init__(self):
                super(SpecificRequestHandler, self).__init__(cls)
        return SpecificRequestHandler
    
    @classmethod
    def request_handler(cls, parent_handler):
        """Returns a RequestHandler instance for this endpoint,
        derived from a parent_handler. This can be used for rewriting requests.
        """
        handler_class = cls.request_handler_class()
        handler = handler_class()
        handler.request = parent_handler.request
        handler.response = parent_handler.response
        return handler
    
    @classmethod
    def upload_request_handler_class(cls):
        """Returns an upload request handler class for this endpoint"""
        class SpecificUploadRequestHandler(_handlers.UploadRequestHandler):
            def __init__(self):
                super(SpecificUploadRequestHandler, self).__init__(cls)
        return SpecificUploadRequestHandler

from google.appengine.ext.webapp.util import run_wsgi_app
def run_wsgi_restapp(endpoint_class):
    """Creates a WSGIApplication for a REST endpoint and runs it.
    Args:
        endpoint_class - a class derived from Endpoint that implements the endpoint
    """
    
    root_url = endpoint_class.get_root_url()
    logging.info("starting a rest endpoint on '%s' with handler: %s" % (root_url, endpoint_class))
    
    map = [('.*/__upload', endpoint_class.upload_request_handler_class()),
           ('.*', endpoint_class.request_handler_class())]

    application = webapp.WSGIApplication(map, debug=True)
    run_wsgi_app(application)
