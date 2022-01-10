import os
import re
import requests
from requests import Request
from urllib.parse import urlparse

from django.http import HttpResponse
from django.http import QueryDict
from django.views.decorators.csrf import csrf_exempt

# TOR_PROXY = '103.36.92.72:3128'
TOR_PROXY = '127.0.0.1:3128'

proxyDict = None

# get proxy type
PROXY_TYPE = os.environ.get('PROXY_TYPE')
# set proxy
if PROXY_TYPE == 'onion':
    proxyDict = {
        "http":   "http://{}".format(TOR_PROXY),
        "https":  "https://{}".format(TOR_PROXY),
        "ftp":    "ftp://{}".format(TOR_PROXY)
    }
elif PROXY_TYPE == 'clear':
    proxyDict = {}

PROXY_ENDPOINT = os.environ.get('PROXY_ENDPOINT')
TARGET_ENDPOINT = os.environ.get('TARGET_ENDPOINT')
# PROXY_ENDPOINT = 'http://103.36.92.72:18000'
# TARGET_ENDPOINT = 'http://dreadytofatroptsdj6io7l3xptbet6onoyno2yv7jicoxknyazubrad.onion'

session = requests.session()


def getCookies(cookie_jar, domain):
    cookie_dict = cookie_jar.get_dict(domain=domain)
    found = ['%s=%s' % (name, value) for (name, value) in cookie_dict.items()]
    return ';'.join(found)


def get_headers(environ):
    """
    Retrieve the HTTP headers from a WSGI environment dictionary.  See
    https://docs.djangoproject.com/en/dev/ref/request-response/#django.http.HttpRequest.META
    """
    headers = {}
    for key, value in environ.items():
        # Sometimes, things don't like when you send the requesting host through.
        if key.startswith('HTTP_') and key != 'HTTP_HOST':
            headers[key[5:].replace('_', '-')] = value
        elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            headers[key.replace('_', '-')] = value

    return headers


def make_absolute_location(base_url, location):
    """
    Convert a location header into an absolute URL.
    """
    absolute_pattern = re.compile(r'^[a-zA-Z]+://.*$')
    if absolute_pattern.match(location):
        return location

    parsed_url = urlparse(base_url)

    if location.startswith('//'):
        # scheme relative
        return parsed_url.scheme + ':' + location

    elif location.startswith('/'):
        # host relative
        return parsed_url.scheme + '://' + parsed_url.netloc + location

    else:
        # path relative
        return parsed_url.scheme + '://' + parsed_url.netloc + parsed_url.path.rsplit('/', 1)[0] + '/' + location

    return location


@csrf_exempt 
def index(request, url, requests_args=None):
    
    """
    Forward as close to an exact copy of the request as possible along to the
    given url.  Respond with as close to an exact copy of the resulting
    response as possible.
    If there are any additional arguments you wish to send to requests, put
    them in the requests_args dictionary.
    """
    requests_args = {}
    headers = get_headers(request.META)

    # add query string
    if 'QUERY_STRING' in request.META:
        url = url + '?' + request.META['QUERY_STRING']

    if 'headers' not in requests_args:
        requests_args['headers'] = {}
    if 'data' not in requests_args:
        requests_args['data'] = request.body
    if 'params' not in requests_args:
        requests_args['params'] = QueryDict('', mutable=True)
        
    if request.method == 'GET':
        params = request.GET.copy()
    elif request.method == 'POST':
        params = request.POST.copy()

    # Overwrite any headers and params from the incoming request with explicitly
    # specified values for the requests library.
    headers.update(requests_args['headers'])
    params.update(requests_args['params'])

    # If there's a content-length header from Django, it's probably in all-caps
    # and requests might not notice it, so just remove it.
    for key in list(headers.keys()):
        if key.lower() in ['content-length', 'cookie']:
            del headers[key]
        if key.lower() in ['referer', 'origin']:
            headers[key] = headers[key].replace(PROXY_ENDPOINT, TARGET_ENDPOINT)

    requests_args['headers'] = headers
    requests_args['params'] = params

    # print(1111, requests_args)
    response = session.request(
        request.method, TARGET_ENDPOINT + "/" + url, 
        **requests_args, 
        allow_redirects=False,
        proxies=proxyDict,
        )
    # print(2222, TARGET_ENDPOINT + "/" + url)
    # print(3333, response.status_code)
    # print(4444, response.history)

    resp_content = response.content

    proxy_response = HttpResponse(
        resp_content.replace(str.encode(TARGET_ENDPOINT), str.encode(PROXY_ENDPOINT)),
        status=response.status_code)

    excluded_headers = set([
        # Hop-by-hop headers
        # ------------------
        # Certain response headers should NOT be just tunneled through.  These
        # are they.  For more info, see:
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.5.1
        'connection', 'keep-alive', 'proxy-authenticate',
        'proxy-authorization', 'te', 'trailers', 'transfer-encoding',
        'upgrade',

        # Although content-encoding is not listed among the hop-by-hop headers,
        # it can cause trouble as well.  Just let the server set the value as
        # it should be.
        'content-encoding',

        # Since the remote server may or may not have sent the content in the
        # same encoding as Django will, let Django worry about what the length
        # should be.
        'content-length',
    ])
    for key, value in response.headers.items():
        if key.lower() in excluded_headers:
            continue
        elif key.lower() == 'location':
            # If the location is relative at all, we want it to be absolute to
            # the upstream server.
            # proxy_response[key] = make_absolute_location(response.url, value)
            proxy_response[key] = value.replace(TARGET_ENDPOINT, PROXY_ENDPOINT)
        else:
            proxy_response[key] = value

    # print(5555, proxy_response.status_code)
    # print(6666, proxy_response)
    return proxy_response