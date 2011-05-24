"""Request and response context objects for the respapp framework"""

import inspect
import errors
import logging

from datetime import timedelta
from datetime import datetime
import utils
from google.appengine.api import blobstore

class RequestContext(object):
    """Represents a request context"""
    def __init__(self, request, response, endpoint_class, root_path_position, root_path):
        """Constructor.
        
        Args:
            request: the request object
            response: the response object
            endpoint_class: the class that implements the endpoint
            resource_path: the path to the resource
        """
        self.endpoint_name = endpoint_class.__name__.lower()
        self.endpoint_file = inspect.getfile(endpoint_class)
        self.request = request
        self.response = response
        self.root_path_position = root_path_position
        self.root_path = root_path
        self.resource_path = self._get_resource_path()
        self.auth_context = None
        self.endpoint_class = endpoint_class

    def require(self, key, msgfmt = "missing required argument '%s'"):
        """Tries to retrieve an argument from the request and if
        it was not provided, raises a bad request.
        Args:
            key - The GET/POST parameter name
            message - The message to emit with the error
        """
        val = self.request.get(key)
        if not val or val == '':
            raise errors.BadRequestError(msgfmt % key);
        return val
    
    def argument(self, key, default_value = None):
        """Retrieves a request argument. Returns the default value if not found
        Args:
            key - the key name
            default_value - the value to return if not defined
        """
        val = self.request.get(key)
        if not val or val == '': return default_value
        return val 
    
    def require_auth(self, message = "Request must be authenticated"):
        """Requires that a request be authenticated (that the auth_context will not be None).
        If not, an unauthorized response is returned
        Returns:
            The authentication context.
        """
        if not self.auth_context:
            raise errors.UnauthorizedRequestError("Request must be authenticated")
        return self.auth_context

    def no_cache(self):
        """Sets the cache headers to no-cache"""
        self.response.headers['Cache-Control'] = 'no-cache'
        self.response.headers['Expires'] = utils.format_http_time(datetime(year = 1970, month = 1, day = 1))

    def cache_expires_in(self, timedelta = timedelta(0)):
        """Sets the Cache-Control header of the response.
        See http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9
        Args:
            timedelta - the time this resource can be cached
        """
        self.response.headers['Expires'] = utils.format_http_time(datetime.utcnow() + timedelta) 
        self.response.headers['Cache-Control'] = 'max-age=%d' % utils.total_seconds(timedelta)
        logging.info('Setting caches to expire after %s' % timedelta)

    def cache_never_expires(self):
        """Sets the Cache-Control and Expired headers to far future"""
        self.cache_expires_in(timedelta(days = 365 * 10)) # about 10 years

    def handle_if_modified_since(self, last_modified):
        """Checks if the request has the 'If-Modified-Since' header and compares it to the
        last_modified datetime. It also emits the 'Last-Modified' header in all responses. 
        """
        # emit the last-modified header
        self.response.headers['Last-Modified'] = utils.format_http_time(last_modified)
        
        # if we got the 'if-modified-since header', raise a 304 if the last modified time
        # is before the last-seen time.
        if 'If-Modified-Since' in self.request.headers:
            ims = self.request.headers['If-Modified-Since']
            if utils.parse_http_time(ims) >= last_modified.replace(microsecond = 0):
                raise errors.NotModifiedError()

    def upload_url(self, query = None):
        """Creates a blob upload URL for this endpoint.
        For all endpoints, we assume that we have an /__upload URL that is bound
        to an blob upload endpoint. This makes implementing upload for an endpoint very easy.
        Args:
            query: query parameters to add (in URL format)
        """
        post_url = self.endpoint_class.construct_relative_url('__upload' + query)
        logging.info('constructed upload url: %s' % post_url)
        url = blobstore.create_upload_url(post_url)
        logging.info('url: %s' % url)
        return url

    def get_uploads(self, *args):
        """Should be called by the 'upload' handler to retrieve the uploads just
        stored in the blobstore.
        """
        raise errors.InternalServerError("'get_uploads' can only be called from the 'upload' handler")
    
    def send_blob(self, *args):
        """May be called to send a blob into the response object.
        Same signature as the App Engine send_blob method.
        """
        raise NotImplementedError("send_blob cannot be called from the 'upload' handler")

    def _get_resource_path(self):
        """Splits the request path and returns the path after the endpoint root
        Returns:
            The entire path after the endpoint root.
            If the path contains multiple parts, it is returned as an array.
            If the path contains a single part, it is returned as a single string value.
        """
        parts = filter(lambda x: x, self.request.path.split('/'))
        if len(parts) <= self.root_path_position:
            return None
        ret = parts[1:]
        if len(ret) == 1: return ret[0]
        else: return ret
