#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Zhibo Liu'

from db import Dict

import types,os,re,cgi,sys,time,datetime,functools,mimetypes,threading,logging,urllib,traceback
import utils

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

#################################################################
# 实现事物数据接口, 实现request 数据和response数据的存储,
# 是一个全局ThreadLocal对象
#################################################################

ctx = threading.local()

_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')
_HEADER_X_POWERED_BY = ('X-Powered-By', 'transwarp/1.0')

#用于时区转换
_TIMEDELTA_ZERO = datetime.timedelta(0) #夏令时
_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')   #'+00:00'
                    # ^字符串开头 $ 字符串结尾
                    #4个组:
                    # ([\+\-])  匹配 +号 或-
                    # ([0-9]{1,2}) 从0到9中匹配1 到2 个数字
                    # \: 匹配:冒号
                    # ([0-9]{1,2})

# response status
_RESPONSE_STATUSES = {
    # Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',

    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}

_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',
)

class UTC(datetime.tzinfo):
    """
       tzinfo 是一个基类，用于给datetime对象分配一个时区
       使用方式是 把这个子类对象传递给datetime.tzinfo属性
       传递方法有2种：
           １.　初始化的时候传入
               datetime(2009,2,17,19,10,2,tzinfo=tz0)
           ２.　使用datetime对象的 replace方法传入，从新生成一个datetime对象
               datetime.replace(tzinfo= tz0）
       >>> tz0 = UTC('+00:00')
       >>> tz0.tzname(None)
       'UTC+00:00'
       >>> tz8 = UTC('+8:00')
       >>> tz8.tzname(None)
       'UTC+8:00'
       >>> tz7 = UTC('+7:30')
       >>> tz7.tzname(None)
       'UTC+7:30'
       >>> tz5 = UTC('-05:30')
       >>> tz5.tzname(None)
       'UTC-05:30'
       >>> from datetime import datetime
       >>> u = datetime.utcnow().replace(tzinfo=tz0)
       >>> l1 = u.astimezone(tz8)
       >>> l2 = u.replace(tzinfo=tz8)
       >>> d1 = u - l1
       >>> d2 = u - l2
       >>> d1.seconds
       0
       >>> d2.seconds
       28800
    """
    def __init__(self, utc):
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1) == '-'
            h = int(mt.group(2))
            m = int(mt.group(3))
            if minus:
                h, m = (-h), (-m)
            self._utcoffset = datetime.timedelta(hours=h,minutes=m)
            self._tzname = 'UTC%s' % utc
        else:
            raise ValueError('bad utc time zone from class UTC __init__')

    def utcoffset(self, date_time):
        """
               表示与标准时区的 偏移量
               """
        return self._utcoffset

    def dst(self, date_time):
        """
                Daylight Saving Time 夏令时
                """
        return _TIMEDELTA_ZERO

    def tzname(self, date_time):
        """
                所在时区的名字
                """
        return self._tzname #如果要把一个类的实例变成 str，就需要实现特殊方法__str__()

    def __str__(self):
        return 'UTC timezone info obj (%s) from class UTC __Str__' % self._tzname

UTC_0 = UTC('+00:00')

#异常处理
class _HttpError(Exception):
    """
        HttpError that defines http error code.
        >>> e = _HttpError(404)
        >>> e.status
        '404 Not Found'
        """
    def __init__(self, code):
        """
                Init an HttpError with response code.
                """
        super(_HttpError,self).__init__()
        self.status = '%d %s' % (code, _RESPONSE_STATUSES[code]) # d 表示打印整数
        self._headers = None

    def header(self,name, value):
        """
                添加header， 如果header为空则 添加powered by header
                """
        if not self._headers:
            self._headers = [_HEADER_X_POWERED_BY]
        self._headers.append(name,value)

    @property
    def headers(self):
        """
                使用setter方法实现的 header属性
                """
        if hasattr(self,'_headers'):
            return self._headers
        return []

    def __str__(self):
        return  self.status

    __repr__ = __str__

class _RedirectError(_HttpError):
    """
        RedirectError that defines http redirect code.
        >>> e = _RedirectError(302, 'http://www.apple.com/')
        >>> e.status
        '302 Found'
        >>> e.location
        'http://www.apple.com/'
        """
    def __init__(self, code, location):
        """
                Init an HttpError with response code.
                """
        super(_RedirectError,self).__init__(code)
        self.location = location

    def __str__(self):
        return '%s %s' % (self.status, self.location)

    __repr__ = __str__


class HttpError(object):
    """
        HTTP Exceptions
        """
    @staticmethod
    def badrequest():
        """
                Send a bad request response.
                >>> raise HttpError.badrequest()
                Traceback (most recent call last):
                  ...
                _HttpError: 400 Bad Request
                """
        return _HttpError(400)

    @staticmethod
    def unauthorized():

        """
        Send an unauthorized response.
        >>> raise HttpError.unauthorized()
        Traceback (most recent call last):
          ...
        _HttpError: 401 Unauthorized
        """
        return _HttpError(401)

    @staticmethod
    def forbidden():
        """
                Send a forbidden response.
                >>> raise HttpError.forbidden()
                Traceback (most recent call last):
                  ...
                _HttpError: 403 Forbidden
                """
        return _HttpError(403)

    @staticmethod
    def notfound():
        """
                Send a not found response.
                >>> raise HttpError.notfound()
                Traceback (most recent call last):
                  ...
                _HttpError: 404 Not Found
                """
        return _HttpError(404)

    @staticmethod
    def conflict():
        """
                Send a conflict response.
                >>> raise HttpError.conflict()
                Traceback (most recent call last):
                  ...
                _HttpError: 409 Conflict
                """
        return _HttpError(409)

    @staticmethod
    def internalerror():
        """
                Send an internal error response.
                >>> raise HttpError.internalerror()
                Traceback (most recent call last):
                  ...
                _HttpError: 500 Internal Server Error
                """
        return _HttpError(500)

    @staticmethod
    def redirect(location):
        """
                Do permanent redirect.
                >>> raise HttpError.redirect('http://www.itranswarp.com/')
                Traceback (most recent call last):
                  ...
                _RedirectError: 301 Moved Permanently, http://www.itranswarp.com/
                """
        return _RedirectError(301,location)

    @staticmethod
    def found(location):
        """
                Do temporary redirect.
                >>> raise HttpError.found('http://www.itranswarp.com/')
                Traceback (most recent call last):
                  ...
                _RedirectError: 302 Found, http://www.itranswarp.com/
                """
        return _RedirectError(302, location)

    @staticmethod
    def seeother(location):
        """
                Do temporary redirect.
                >>> raise HttpError.seeother('http://www.itranswarp.com/')
                Traceback (most recent call last):
                  ...
                _RedirectError: 303 See Other, http://www.itranswarp.com/
                >>> e = HttpError.seeother('http://www.itranswarp.com/seeother?r=123')
                >>> e.location
                'http://www.itranswarp.com/seeother?r=123'
                """
        return _RedirectError(303, location)

_RESPONSE_HEADER_DICT = dict(zip(map(lambda x:x.upper(),_RESPONSE_HEADERS),_RESPONSE_HEADERS))


class MultipartFile(object):
    """
       Multipart file storage get from request input.
       f = ctx.request['file']
       f.filename # 'test.png'
       f.file # file-like object
       """
    def __init__(self, storage):
        self.filename = utils.to_unicode(storage.filename)
        self.file = storage.file

class Request(object):
    """
        请求对象， 用于获取所有http请求信息。
        """
    def __init__(self, environ):
        """
               environ  wsgi处理函数里面的那个 environ
               wsgi server调用 wsgi 处理函数时传入的
               包含了用户请求的所有数据
               """
        self._environ = environ

    def _parse_input(self):
        """
                将通过wsgi 传入过来的参数，解析成一个字典对象 返回
                比如： Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
                    这里解析的就是 wsgi.input 对象里面的字节流
                """
        def _convert(item):
            if isinstance(item,list):
                return [utils.to_unicode(i.value) for i in item]
            if item.filename:
                return MultipartFile(item)
            return utils.to_unicode(item.value)
        #_environ 可以理解为环境变量 包含了用户请求的所有数据
        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ,keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    def _get_raw_input(self):
        """
                将从wsgi解析出来的 数据字典，添加为Request对象的属性
                然后 返回该字典
                """
        if not hasattr(self,'_raw_input'):
            self._raw_input = self._parse_input()
        return self._raw_input

    def __getitem__(self, key):
        """
                实现通过键值访问Request对象里面的数据，如果该键有多个值，则返回第一个值
                如果键不存在，这会 raise KyeError
                >>> from StringIO import StringIO
                >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
                >>> r['a']
                u'1'
                >>> r['c']
                u'ABC'
                >>> r['empty']
                Traceback (most recent call last):
                    ...
                KeyError: 'empty'
                >>> b = '----WebKitFormBoundaryQQ3J8kPsjFpTmqNz'
                >>> pl = ['--%s' % b, 'Content-Disposition: form-data; name=\\"name\\"\\n', 'Scofield', '--%s' % b, 'Content-Disposition: form-data; name=\\"name\\"\\n', 'Lincoln', '--%s' % b, 'Content-Disposition: form-data; name=\\"file\\"; filename=\\"test.txt\\"', 'Content-Type: text/plain\\n', 'just a test', '--%s' % b, 'Content-Disposition: form-data; name=\\"id\\"\\n', '4008009001', '--%s--' % b, '']
                >>> payload = '\\n'.join(pl)
                >>> r = Request({'REQUEST_METHOD':'POST', 'CONTENT_LENGTH':str(len(payload)), 'CONTENT_TYPE':'multipart/form-data; boundary=%s' % b, 'wsgi.input':StringIO(payload)})
                >>> r.get('name')
                u'Scofield'
                >>> r.gets('name')
                [u'Scofield', u'Lincoln']
                >>> f = r.get('file')
                >>> f.filename
                u'test.txt'
                >>> f.file.read()
                'just a test'
                """
        r = self._get_raw_input()[key]
        if isinstance(r,list):
            return r[0]
        return r
    def get(self,key,default=None):
        """
                实现了字典里面的get功能
                和上面的__getitem__一样(request[key]),但如果没有找到key,则返回默认值。
                >>> from StringIO import StringIO
                >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
                >>> r.get('a')
                u'1'
                >>> r.get('empty')
                >>> r.get('empty', 'DEFAULT')
                'DEFAULT'
                """
        r = self._get_raw_input().get(key,default)
        if isinstance(r,list):
            return r[0]
        return r

    def gets(self,key):
        '''
                Get multiple values for specified key.
                >>> from StringIO import StringIO
                >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
                >>> r.gets('a')
                [u'1']
                >>> r.gets('c')
                [u'ABC', u'XYZ']
                >>> r.gets('empty')
                Traceback (most recent call last):
                    ...
                KeyError: 'empty'
                '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[:]
        return [r]

    def input(self,**kw):
        """
                返回一个由传入的数据和从environ里取出的数据 组成的Dict对象，Dict对象的定义 见db模块
                Get input as dict from request, fill dict using provided default value if key not exist.
                i = ctx.request.input(role='guest')
                i.role ==> 'guest'
                >>> from StringIO import StringIO
                >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
                >>> i = r.input(x=2008)
                >>> i.a
                u'1'
                >>> i.b
                u'M M'
                >>> i.c
                u'ABC'
                >>> i.x
                2008
                >>> i.get('d', u'100')
                u'100'
                >>> i.x
                2008
                """
        copy = Dict(**kw)
        raw = self._get_raw_input()
        for k,v in raw.iteritems():
            copy[k] = v[0] if isinstance(v,list) else v
        return  copy

    def get_body(self):
        """
                从HTTP POST 请求中取得 body里面的数据，返回为一个str对象
                >>> from StringIO import StringIO
                >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('<xml><raw/>')})
                >>> r.get_body()
                '<xml><raw/>'
        """
        fp = self._environ['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        """
                Get remote addr. Return '0.0.0.0' if cannot get remote_addr.
                >>> r = Request({'REMOTE_ADDR': '192.168.0.100'})
                >>> r.remote_addr
                '192.168.0.100'
                """
        return self._environ.get('REMOTE_ADDR','0.0.0.0')

    @property
    def document_root(self):
        """
                Get raw document_root as str. Return '' if no document_root.
                >>> r = Request({'DOCUMENT_ROOT': '/srv/path/to/doc'})
                >>> r.document_root
                '/srv/path/to/doc'
                """
        return self._environ.get('DOCUMENT_ROOT','')

    @property
    def query_string(self):
        """
                Get raw query string as str. Return '' if no query string.
                >>> r = Request({'QUERY_STRING': 'a=1&c=2'})
                >>> r.query_string
                'a=1&c=2'
                >>> r = Request({})
                >>> r.query_string
                ''
                """
        return self._environ.get('QUERY_STRING','')

    @property
    def environ(self):
        """
                Get raw environ as dict, both key, value are str.
                >>> r = Request({'REQUEST_METHOD': 'GET', 'wsgi.url_scheme':'http'})
                >>> r.environ.get('REQUEST_METHOD')
                'GET'
                >>> r.environ.get('wsgi.url_scheme')
                'http'
                >>> r.environ.get('SERVER_NAME')
                >>> r.environ.get('SERVER_NAME', 'unamed')
                'unamed'
                """
        return self._environ

    @property
    def request_method(self):
        """
                Get request method. The valid returned values are 'GET', 'POST', 'HEAD'.
                >>> r = Request({'REQUEST_METHOD': 'GET'})
                >>> r.request_method
                'GET'
                >>> r = Request({'REQUEST_METHOD': 'POST'})
                >>> r.request_method
                'POST'
                """
        return self._environ['REQUEST_METHOD']

    @property
    def path_info(self):
        """
                Get request path as str.
                >>> r = Request({'PATH_INFO': '/test/a%20b.html'})
                >>> r.path_info
                '/test/a b.html'
                """
        return urllib.unquote(self._environ.get('PATH_INFO',''))

    @property
    def host(self):
        """
                Get request host as str. Default to '' if cannot get host..
                >>> r = Request({'HTTP_HOST': 'localhost:8080'})
                >>> r.host
                'localhost:8080'
                """
        return self._environ.get('HTTP_HOST','')

    def _get_headers(self):
        """
                从environ里 取得HTTP_开通的 header
                """
        if not hasattr(self,'_headers'):
            hdrs = {}
            for k,v in self._environ.iteriterms():
                if k.startswith('HTTP_'):
                    # convert 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
                    hdrs[k[5:].replace('_','-').upper()] = v.decode('utf-8')
            self._headers = hdrs
        return self._headers

    @property
    def headers(self):
        """
                获取所有的header， setter实现的属性
                Get all HTTP headers with key as str and value as unicode. The header names are 'XXX-XXX' uppercase.
                >>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
                >>> H = r.headers
                >>> H['ACCEPT']
                u'text/html'
                >>> H['USER-AGENT']
                u'Mozilla/5.0'
                >>> L = H.items()
                >>> L.sort()
                >>> L
                [('ACCEPT', u'text/html'), ('USER-AGENT', u'Mozilla/5.0')]
                """
        return dict(**self._get_headers())

    def header(self,header,default=None):
        """
                获取指定的header的值
                Get header from request as unicode, return None if not exist, or default if specified.
                The header name is case-insensitive such as 'USER-AGENT' or u'content-Type'.
                >>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
                >>> r.header('User-Agent')
                u'Mozilla/5.0'
                >>> r.header('USER-AGENT')
                u'Mozilla/5.0'
                >>> r.header('Accept')
                u'text/html'
                >>> r.header('Test')
                >>> r.header('Test', u'DEFAULT')
                u'DEFAULT'
                """
        return self._get_headers().get(header.upper(),default)

    def _get_cookies(self):
        """
                从environ里取出cookies字符串，并解析成键值对 组成的字典
                """
        if not hasattr(self,'_cookies'):
            cookies = {}
            cookie_str = self._environ.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):
                    pos = c.find('=')
                    if pos > 0:
                        cookies[c[:pos].strip()] = utils.unquote(c[pos+1:])
            self._cookies = cookies
        return self._cookies

    @property
    def cookies(self):
        """
                setter 以Dict对象返回cookies
                Return all cookies as dict. The cookie name is str and values is unicode.
                >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
                >>> r.cookies['A']
                u'123'
                >>> r.cookies['url']
                u'http://www.example.com/'
                """
        return Dict(**self._get_cookies())

    def cookie(self,name,default=None):
        """
                获取指定的cookie
                Return specified cookie value as unicode. Default to None if cookie not exists.
                >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
                >>> r.cookie('A')
                u'123'
                >>> r.cookie('url')
                u'http://www.example.com/'
                >>> r.cookie('test')
                >>> r.cookie('test', u'DEFAULT')
                u'DEFAULT'
                """
        return self._get_cookies().get(name,default)


class Response(object):

    def __init__(self):
        self._status = '200 OK'
        self._headers = {'CONTENT-TYPE': 'text/html; charset=utf-8'}

    def unset_header(self,name):
        """
                删除指定的header
                >>> r = Response()
                >>> r.header('content-type')
                'text/html; charset=utf-8'
                >>> r.unset_header('CONTENT-type')
                >>> r.header('content-type')
                """
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self,name,value):
        """
                给指定的header 赋值
                >>> r = Response()
                >>> r.header('content-type')
                'text/html; charset=utf-8'
                >>> r.set_header('CONTENT-type', 'image/png')
                >>> r.header('content-TYPE')
                'image/png'
                """
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = utils.to_str(value)

    def header(self,name):
        """
                获取Response Header 里单个 Header的值， 非大小写敏感
                >>> r = Response()
                >>> r.header('content-type')
                'text/html; charset=utf-8'
                >>> r.header('CONTENT-type')
                'text/html; charset=utf-8'
                >>> r.header('X-Powered-By')
                """
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    @property
    def headers(self):
        """
                setter 构造的属性，以[(key1, value1), (key2, value2)...] 形式存储 所有header的值，
                包括cookies的值
                >>> r = Response()
                >>> r.headers
                [('Content-Type', 'text/html; charset=utf-8'), ('X-Powered-By', 'transwarp/1.0')]
                >>> r.set_cookie('s1', 'ok', 3600)
                >>> r.headers
                [('Content-Type', 'text/html; charset=utf-8'), ('Set-Cookie', 's1=ok; Max-Age=3600; Path=/; HttpOnly'), ('X-Powered-By', 'transwarp/1.0')]
                """
        L = [(_RESPONSE_HEADER_DICT.get(k,k),v) for k,v in self._headers.iteritems()]
        if hasattr(self,'_cookies'):
            for v in self._cookies.itervalues():
                L.append(('Set-Cookie',v))
        L.append(_HEADER_X_POWERED_BY)
        return L

    @property
    def content_type(self):
        """
                setter 方法实现的属性，用户保存header： Content-Type的值
                >>> r = Response()
                >>> r.content_type
                'text/html; charset=utf-8'
                >>> r.content_type = 'application/json'
                >>> r.content_type
                'application/json'
                """
        return self.header('CONTENT-TYPE')
    @content_type.setter
    def content_type(self,value):
        '''@property可以将python定义的函数“当做”属性访问，从而提供更加友好访问方式，但是有时候setter/deleter也是需要的。
                1》只有@property表示只读。
                2》同时有@property和@x.setter表示可读可写。
                3》同时有@property和@x.setter和@x.deleter表示可读可写可删除。
            '''

        """
                让content_type 属性可写， 及设置Content-Type Header
                """
        if value:
            self.set_header('CONTENT-TYPE',value)
        else:
            self.unset_header('CONTENT-TYPE')

    @property
    def content_length(self):
        """
                获取Content-Length Header 的值
                >>> r = Response()
                >>> r.content_length
                >>> r.content_length = 100
                >>> r.content_length
                '100'
                """
        return self.header('CONTENT-LENGTH')

    @content_length.setter
    def content_length(self,value):
        """
                设置Content-Length Header 的值
                >>> r = Response()
                >>> r.content_length = '1024'
                >>> r.content_length
                '1024'
                >>> r.content_length = 1024 * 8
                >>> r.content_length
                '8192'
                """
        self.set_header('CONTENT-LENGTH', str(value))

    def delete_cookie(self,name):
        """
                Delete a cookie immediately.
                Args:
                  name: the cookie name.
                """
        self.set_cookie(name,'__deleted__', expires=0)

    def set_cookie(self,name,value,max_age=None,expires=None,path='/',domain=None,secure=False,http_ony=True):
        """
                Set a cookie.
                Args:
                  name: the cookie name.
                  value: the cookie value.
                  max_age: optional, seconds of cookie's max age.
                  expires: optional, unix timestamp, datetime or date object that indicate an absolute time of the
                           expiration time of cookie. Note that if expires specified, the max_age will be ignored.
                  path: the cookie path, default to '/'.
                  domain: the cookie domain, default to None.
                  secure: if the cookie secure, default to False.
                  http_only: if the cookie is for http only, default to True for better safty
                             (client-side script cannot access cookies with HttpOnly flag).
                >>> r = Response()
                >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
                >>> r._cookies
                {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
                >>> r.set_cookie('company', r'Example="Limited"', expires=1342274794.123, path='/sub/')
                >>> r._cookies
                {'company': 'company=Example%3D%22Limited%22; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/sub/; HttpOnly'}
                >>> dt = datetime.datetime(2012, 7, 14, 22, 6, 34, tzinfo=UTC('+8:00'))
                >>> r.set_cookie('company', 'Expires', expires=dt)
                >>> r._cookies
                {'company': 'company=Expires; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/; HttpOnly'}
                """
        if not hasattr(self,'_cookie'):
            self._cookies = {}
        L = ['%s=%s' & (utils.quote(name),utils.quote(value))]
        if expires is not None:
            if isinstance(expires,(float,int,long)):
                L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires,UTC_0).strftime('%a, %d-%b-%y %H:%M:%S GMT'))
            if isinstance(expires,(datetime.date,datetime.datetime)):
                L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%y %H:%M:%S GMT'))
        elif isinstance(max_age,(int,long)):
            L.append('Max-Age=%d' % max_age)
        L.append('Path=%s' % path)
        if domain:
            L.append('Domain=%s' % domain)
        if secure:
            L.append('Secure')
        if http_ony:
            L.append('HttpOnly')
        self._cookies[name] = '; '.join(L)

    def unset_cookie(self,name):
        """
                Unset a cookie.
                >>> r = Response()
                >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
                >>> r._cookies
                {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
                >>> r.unset_cookie('company')
                >>> r._cookies
                {}
                """
        if hasattr(self,'_cookies'):
            if name in self._cookies:
                del self._cookies[name]

    @property
    def status_code(self):
        """
                Get response status code as int.
                >>> r = Response()
                >>> r.status_code
                200
                >>> r.status = 404
                >>> r.status_code
                404
                >>> r.status = '500 Internal Error'
                >>> r.status_code
                500
                """
        return int(self._status[:3])

    @property
    def status(self):
        """
               Get response status. Default to '200 OK'.
               >>> r = Response()
               >>> r.status
               '200 OK'
               >>> r.status = 404
               >>> r.status
               '404 Not Found'
               >>> r.status = '500 Oh My God'
               >>> r.status
               '500 Oh My God'
               """
        return self._status
    @status.setter
    def status(self,value):
        """
                Set response status as int or str.
                >>> r = Response()
                >>> r.status = 404
                >>> r.status
                '404 Not Found'
                >>> r.status = '500 ERR'
                >>> r.status
                '500 ERR'
                >>> r.status = u'403 Denied'
                >>> r.status
                '403 Denied'
                >>> r.status = 99
                Traceback (most recent call last):
                  ...
                ValueError: Bad response code: 99
                >>> r.status = 'ok'
                Traceback (most recent call last):
                  ...
                ValueError: Bad response code: ok
                >>> r.status = [1, 2, 3]
                Traceback (most recent call last):
                  ...
                TypeError: Bad type of response code.
                """
        if isinstance(value,(int,long)):
            if 100<= value<=999:
                st = _RE_RESPONSE_STATUS.get(value,'')
                if st:
                    self._status = '%d %s' %(value, st)
                else:
                    self._status = str(value)
            else:
                raise ValueError('bad response code from class response status.setter: %d' % value)
        elif isinstance(value,basestring):
            if isinstance(value,unicode):
                value = value.encode('utf-8')
            if _RE_RESPONSE_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('bad response code from class response status.setter: %s' % value)
        else:
            raise TypeError('bad type of response code from class response status.setter')




#################################################################
# 实现URL路由功能
# 将URL 映射到 函数上
#################################################################
_re_route = re.compile(r'(:[a-zA-Z_]\w*)')

# 方法的装饰器，用于捕获url
def get(path):
    """
        A @get decorator.
        @get('/:id')
        def index(id):
            pass
        >>> @get('/test/:id')
        ... def test():
        ...     return 'ok'
        ...
        >>> test.__web_route__
        '/test/:id'
        >>> test.__web_method__
        'GET'
        >>> test()
        'ok'
        """
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'GET'
        return func
    return _decorator

def post(path):
    """
        A @post decorator.
        >>> @post('/post/:id')
        ... def testpost():
        ...     return '200'
        ...
        >>> testpost.__web_route__
        '/post/:id'
        >>> testpost.__web_method__
        'POST'
        >>> testpost()
        '200'
        """
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func
    return _decorator

def _build_regex(path):
    r"""
        用于将路径转换成正则表达式，并捕获其中的参数
        >>> _build_regex('/path/to/:file')
        '^\\/path\\/to\\/(?P<file>[^\\/]+)$'
        >>> _build_regex('/:user/:comments/list')
        '^\\/(?P<user>[^\\/]+)\\/(?P<comments>[^\\/]+)\\/list$'
        >>> _build_regex(':id-:pid/:w')
        '^(?P<id>[^\\/]+)\\-(?P<pid>[^\\/]+)\\/(?P<w>[^\\/]+)$'
        """
    re_list = ['^']
    var_list = []
    is_var = False
    for v in _re_route.split(path):
        if is_var:
            var_name = v[1:]
            var_list.append(var_name)
            re_list.append(r'(?P<%s>[^\/]+' % var_name)
        else:
            s =''
            for ch in v:
                if '0' <= ch <= '9':
                    s +=ch
                elif 'A' <= ch <= 'Z':
                    s += ch
                elif 'a' <= ch <= 'z':
                    s += ch
                else:
                    s = s + '\\' + ch
            re_list.append(s)
        is_var = not is_var
    re_list.append('$')
    return ''.join(re_list)

def _static_file_generator(fpath, block_size=8192):
    """
        读取静态文件的一个生成器
        """
    with open(fpath, 'rb') as f:
        block = f.read(block_size)
        while block_size:
            yield block
            block=f.read(block_size)

class Route(object):
    """
        动态路由对象，处理 装饰器捕获的url 和 函数
        比如：
                @get('/:id')
                    def index(id):
                    pass
        在构造器中 path、method、is_static、route 和url相关
        而 func 则指的装饰器里的func，比如上面的index函数
        """
    def __init__(self,func):
        """
                path： 通过method的装饰器捕获的path
                method： 通过method装饰器捕获的method
                is_static： 路径是否含变量，含变量为True
                route：动态url（含变量）则捕获其变量的 re
                func： 方法装饰器里定义的函数
                """
        self.path = func.__web_route__
        self.method = func.__web_method__
        self.is_static = _re_route.search(self.path) is None
        if not self.is_static:
            self.route = re.compile(_build_regex(self.path))
        self.func =func

    def match(self,url):
        """
                传入url，返回捕获的变量
                """
        m = self.route.match(url)
        if m:
            return m.groups()
        return None











































