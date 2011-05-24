import urllib
import logging
import restapp
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from django.utils import simplejson as json

class FacebookQuery:
    TOKEN_CACHE_TTL_SEC = 60 * 30 # 30 minutes
    GRAPH_URL_BASE = "https://graph.facebook.com"
    
    def __init__(self):
        self.cache = memcache.Client()
    
    def graph_url(self, url, **args):
        return '%s/%s?%s' % (self.GRAPH_URL_BASE, url, urllib.urlencode(args))

    def authenticated_graph_url(self, url, access_token, **args):
        return self.graph_url(url, access_token = access_token, **args)

    def _fetch_facebook_graph(self, url, **args):
        url = self.graph_url(url, **args)
        logging.info('facebook graph url: %s' % url)
        result = self.cache.get(url)
        if not result:
            logging.info('fetching: %s' % url)
            fetch_response = urlfetch.fetch(url)
            self.last_response = fetch_response
            if fetch_response.status_code != 200:
                self.last_error = fetch_response.content
                logging.error('facebook error %d: %s' % (fetch_response.status_code, fetch_response.content))
                return None
            result = fetch_response.content
            self.cache.add(url, result)

        return json.loads(result)
    
    def me_from_uid(self, uid):
        return self._fetch_facebook_graph(uid)
            
    def me_from_token(self, access_token):
        return self._fetch_facebook_graph('me', access_token = access_token)

def get_current_user(request, raise_unauthorized = False):
    result = None
    fbquery = FacebookQuery()
    access_token = request.get('fb_access_token')
    
    if not access_token and raise_unauthorized:
        raise request.UnauthorizedRequestError('Authorization required')
    
    if access_token:
        result = fbquery.me_from_token(access_token)
        if not result:
            raise request.UnauthorizedRequestError('Facebook authorization error (%d): %s' % (fbquery.last_response, fbquery.last_error))
    
    return result

def get_current_uid(request, raise_unauthorized = False):
    current_user = get_current_user(request, raise_unauthorized)
    if not current_user: 
        return None

    return current_user['id']

class AuthenticatedEndpoint(restapp.Endpoint):
    """A Facebook-authenticated endpoint.
    All requests that have a fb_access_token parameter will be validated with facebook
    and the facebook 'me' dictionary will be added to the context
    """
    def authenticate_request(self, ctx):
        """Authenticates a request with facebook (in case it has an fb_access_token parameter.
        Args:
            ctx - The request context
        Returns:
            The facebook 'me' object
        """
        fb_access_token = ctx.request.get('fb_access_token')
        if fb_access_token:
            fbquery = FacebookQuery()
            me = fbquery.me_from_token(fb_access_token)
            
            if not me:
                raise restapp.errors.UnauthorizedRequestError('Invalid authentication token (%d): %s' % (fbquery.last_response.status_code, fbquery.last_response.content))
            
            if me: me['access_token'] = fb_access_token
            return me
        return None