from google.appengine.api import datastore_types
import datetime

def parse_timestamp(s):
    if s == None: return None
    if isinstance(s, datetime.datetime): return s   # idempotent for datetimes
    if s.lower() == 'now': return utcnow()          # support 'now'
    
    allowed_formats = [ '%Y-%m-%d %H:%M:%S.%f', 
                        '%Y-%m-%d %H:%M:%S',
                        '%Y-%m-%d %H:%M',
                        '%Y-%m-%d',
                        '%m/%d/%Y',
                        '%m/%d/%Y %H:%M:%S' ]
    
    ts = None
    
    for fmt in allowed_formats:
        try: 
            ts = datetime.datetime.strptime(s, fmt)
            break
        except ValueError: 
            pass
    
    return ts

def utcnow():
    return datetime.datetime.utcnow()

def format(t):
    return t.strftime('%Y-%m-%d %H:%M:%S.%f')

def formatted_now():
    return format(utcnow())

def total_seconds(timedelta):
    """Calculates the total number of seconds in a timedelta object"""
    td = timedelta
    total_seconds = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6
    return total_seconds


HTTP_DATE_FMT = "%a, %d %b %Y %H:%M:%S GMT"

def parse_http_time(timestring):
    """Parses a string in RFC 1123 date format.
    Returns:
        datetime.datetime
    """
    return datetime.datetime.strptime(timestring, HTTP_DATE_FMT)

def format_http_time(dt):
    """Formats a datetime object as RFC 1123 (HTTP/1.1) time format
    Args:
        dt - a datetime object (e.g. datetime.now())
    """
    return dt.strftime(HTTP_DATE_FMT)


def to_dict(model, keyname = None):
    """Converts a model object to a dictionary
    Args:
        model - a model object
        keyname - the key to use if you want to incoporate the model's key name in the dictionary
    Returns:
        A dictionary.
    """
    
    d = dict()
    
    for prop_name in model.properties():
        prop_value = getattr(model, prop_name)

        if prop_value:
            if prop_value.__class__ == datastore_types.Blob: 
                continue # skip blobs
            
            if getattr(prop_value, '__iter__', False): 
                d[prop_name] = prop_value # do not stringify iterables
            else: 
                d[prop_name] = unicode(prop_value)

    if keyname:
        d[keyname] = model.key().name()

    return d    