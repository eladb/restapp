"""Request handlers for the restapp framework"""

from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext import webapp

import errors
import logging
import traceback
import context

class RequestHandlerBase(webapp.RequestHandler):
    def __init__(self, endpoint_class):
        self.endpoint_class = endpoint_class
        self.endpoint = self.endpoint_class()
        self.root_path = self.endpoint_class.get_root_url()
        self.root_path_position = len(filter(lambda x: x, self.root_path.split('/'))) # calculate position of root path
    
    def with_error_handling(self, code):
        """Runs 'code(ctx)' with request error handling.
        Args:
            code - The method to run
        """
        try:
            ctx = self._create_context()
            auth_ctx = self.endpoint.authenticate_request(ctx)
            ctx.auth_context = auth_ctx
            code(ctx)
        except errors.RequestError, e:
            logging.info('HTTP response (%d): %s' % (e.code, e.body))
            if e.code == 500:
                logging.error(traceback.format_exc())
            
            self.response.clear()
            ctx.no_cache() # don't cache these results!
            self.error(e.code)
            self.response.out.write(e.body)
    
    def _create_context(self):
        query_start = self.request.url.find('?')
        if query_start == -1: query_start = None
        self.request.full_path = self.request.url[:query_start]
        
        """Creates a request context"""
        ctx = context.RequestContext(request = self.request, 
                                      response = self.response, 
                                      endpoint_class = self.endpoint_class,
                                      root_path_position = self.root_path_position,
                                      root_path = self.root_path)

        # alias the 'send_blob' and 'get_uploads' methods into the context.
                
        if hasattr(self, 'send_blob'):
            ctx.send_blob = self.send_blob
            
        if hasattr(self, 'get_uploads'):
            def get_uploads(field_name):
                logging.error('here:%s' % field_name)
                return self.get_uploads(field_name)
            ctx.get_uploads = get_uploads
        
        return ctx

class UploadRequestHandler(RequestHandlerBase, blobstore_handlers.BlobstoreUploadHandler):
    def __init__(self, endpoint_class):
        """Initializes the upload request handler.
        Args:
            endpoint_class - the endpoint implementation class
        """
        super(UploadRequestHandler, self).__init__(endpoint_class)
        blobstore_handlers.BlobstoreUploadHandler.__init__(self)
            
    def get(self):
        def safe_get(ctx):
            raise errors.BadRequestError('GET is not supported for this special __upload endpoint')
        self.with_error_handling(safe_get)
    
    def post(self):
        def safe_post(ctx):
            relative_url = self.endpoint.upload(ctx)
            self.redirect(self.endpoint_class.construct_relative_url(relative_url))

        self.with_error_handling(safe_post)

class RequestHandler(RequestHandlerBase, blobstore_handlers.BlobstoreDownloadHandler):
    """Handler that handles REST requests for a specified endpoint"""
    
    def __init__(self, endpoint_class, default_alt = 'html'):
        """Constructor.
        Args:
          endpoint_class: The class that implements the endpoint
          default_alt: The default 'alt' representation to be used if no '?alt' argument is specified 
          root_path_position: The position of the path root
                              E.g: if the URLs look like this '/user/xxx' the root
                              is the 'user' and it's position is 1.
        """
        super(RequestHandler, self).__init__(endpoint_class)
        blobstore_handlers.BlobstoreDownloadHandler.__init__(self)
        self.default_alt = default_alt
    
    def get(self):
        """Handles GET requests by propogating them to the endpoint object."""
        
        def safe_get(ctx):
            response_obj = None
            alt_method_prefix = 'alt_'
    
            # determine if this is a query or a single entity get
            if not ctx.resource_path: # query
                try:
                    response_obj = self.endpoint.query(ctx)
                    alt_method_prefix = 'alt_query_'
                except NotImplementedError:
                    raise errors.BadRequestError('GET is not supported for this endpoint')
            else: # single entity
                try:
                    response_obj = self.endpoint.get(ctx)
                    alt_method_prefix = 'alt_'
                except NotImplementedError:
                    raise errors.BadRequestError('GET is not supported for this endpoint')
    
            # determine representation and invoke the 'alt' method which emits 
            # output to into the response object
            alt = self.request.get('alt', default_value = self.default_alt)
            self._invoke_alt_method(alt, ctx, response_obj, alt_method_prefix)
            
        self.with_error_handling(safe_get)
        
    def post(self):
        """Handles POST requests by propagating them to the endpoint object."""

        def safe_post(ctx):
            try:
                new_resource = self.endpoint.post(ctx)
                self.redirect('%s/%s?alt=json' % (self.root_path, new_resource))
            except NotImplementedError:
                self.error(400)
                self.response.out.write('POST is not supported for this endpoint')

        self.with_error_handling(safe_post)
    
    def _invoke_alt_method(self, alt, ctx, obj, method_name_prefix = 'alt_'):
        """Invokes the alt_XXX method based on a string
        
        Args:
            alt - An 'alt' string (e.g. 'html', 'json', ...)
            respctx - The response context
        """
        
        alt_method = getattr(self.endpoint, '%s%s' % (method_name_prefix, alt.lower()), None)
        if not alt_method:
            self.error(400)
            self.response.out.write('unable to represent resource in format: %s' % alt)
            return

        alt_method(ctx, obj)        
        
        
    