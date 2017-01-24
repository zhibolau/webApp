#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import threading

import time
import uuid

import functools

__author__ = 'Zhibo Liu'

#engine对象持有数据库连接
engine = None


class DBError(Exception):
    pass

class MultiColumnError(DBError):
    pass

'''
def foo(*args, **kwargs):
    print 'args = ', args
    print 'kwargs = ', kwargs
    print '---------------------------------------'

if __name__ == '__main__':
    foo(1,2,3,4)
    foo(a=1,b=2,c=3)
    foo(1,2,3,4, a=1,b=2,c=3)
    foo('a', 1, None, a=1, b='2', c=3)
输出结果如下：
args =  (1, 2, 3, 4)
kwargs =  {}
---------------------------------------
args =  ()
kwargs =  {'a': 1, 'c': 3, 'b': 2}
---------------------------------------
args =  (1, 2, 3, 4)
kwargs =  {'a': 1, 'c': 3, 'b': 2}
---------------------------------------
args =  ('a', 1, None)
kwargs =  {'a': 1, 'c': 3, 'b': '2'}
---------------------------------------

可以看到，这两个是python中的可变参数。*args表示任何多个无名参数，它是一个tuple；**kwargs表示关键字参数，它是一个dict。
并且同时使用*args和**kwargs时，必须*args参数列要在**kwargs前，像foo(a=1, b='2', c=3, a', 1, None, )这样调用的话，
会提示语法错误“SyntaxError: non-keyword arg after keyword arg”。
'''
def create_engine(user, password, database, host='127.0.0.1', port = 3306, **kw):
    import mysql.connector
    #为一个定义在函数外的变量赋值 就要告诉python此变量为global的
    global engine
    if engine is not None:
        raise DBError('Engine has already existed.')
    params = dict(user = user, password = password, database = database, host = host, port = port)
    defaults = dict(use_unicode=True, charset='utf8', collation='utf8_general_ci', autocommit=False)
    #kw 若与default有重叠,把kw中值删去 并且更新default的值为kw的值
    for k, v in defaults.iteritems():
        params[k] = kw.pop(k,v) # kw should be a dict, if k is in kw, remove k and v from kw, and return kw[k]
                                # if k is not in kw, return v which is a default value
                                # if a default v is not provided, error will be raised
    params.update(kw) # key value pair,kw, is added into params
    params['buffered'] = True  #?????????????????????????????????????????
    engine = _Engine(lambda: mysql.connector.connect(**params))
    #test connect.........
    logging.info('init mysql engine <%s> ok. ' % hex(id(engine)))

'''
_xxx       不能用'from module import *'导入

__xxx__  系统定义名字

__xxx     类中的私有变量名

'''

class _Engine(object):
    def __init__(self,connect):
        self._connect = connect

    def connect(self):
        return self._connect()

def next_id(t=None):
    #create an unique id
    #由 当前时间 + 随机数（由伪随机数得来）拼接得到
    if t is None:
        t = time.time()
    return '%015d%s000' %(int(t*1000), uuid.uuid4().hex)

def _profiling(start, sql =''):
    # 计算sql执行时间
    t = time.time() - start
    if t > 0.1:
        logging.warning('[PROFILING] [DB] %s: %s' % (t,sql))
    else:
        logging.info('[PROFILING] [DB] %s: %s' % (t,sql))


class _LasyConnection(object):
    def __init__(self):
        self.connection = None
    def cursor(self):
        if self.connection is None:
            connection = engine.connect()
            logging.info('[CONNECTION][OPEN] connection <%s>...' % hex(id(connection)))
            self.connection = connection
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def cleanup(self):
        if self.connection:
            connection = self.connection
            self.connection = None
            logging.info('[CONNECTION][CLOSE] connection <%s>...' % hex(id(connection)))
            connection.close()


class _DbCtx(threading.local):
    '''
    db模块的核心对象, 数据库连接的上下文对象，负责从数据库获取和释放连接
    取得的连接是惰性连接对象，因此只有调用cursor对象时，才会真正获取数据库连接
    该对象是一个 Thread local对象，因此绑定在此对象上的数据 仅对本线程可见
    '''
    def __init__(self):
        self.connection = None
        self.transactions = 0

    def is_init(self):
        #if current obj is in initialization state
        return self.connection is not None

    def init(self):
        logging.info('open lazy connection....')
        self.connection = _LasyConnection()
        self.transactions = 0

    def cleanup(self):
        #清理连接对象 关闭连接
        self.connection.cleanup()
        self.connection = None

    def cursor(self):
        #get cursor对象 真正取得db连接
        return self.connection.cursor()


_db_ctx = _DbCtx()

def connection():
    """
       db模块核心函数，用于获取一个数据库连接
       通过_ConnectionCtx对 _db_ctx封装，使得惰性连接可以自动获取和释放，
       也就是可以使用 with语法来处理数据库连接
       _ConnectionCtx    实现with语法 实现了连接!!!自动!!!获取释放惰性连接
       ^
       |
       _db_ctx           _DbCtx实例
       ^
       |
       _DbCtx            实现连接获取和释放惰性连接
       ^
       |
       _LasyConnection   实现惰性连接 仅当需要cursor时候 才连接数据库


       所以说惰性连接是基础!!!!!!!!!!!
   """
    return _ConnectionCtx()

def with_connection(func):
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        with _ConnectionCtx():
            return func(*args, **kw)
    return _wrapper

class _ConnectionCtx(object):
    def __enter__(self):
        #get 惰性连接
        global _db_ctx
        self.should_cleanup = False
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.should_cleanup = True
        return self

    def __exit__(self,exctype, excvalue, traceback):
        #release connection
        global _db_ctx
        if self.should_cleanup:
            _db_ctx.cleanup()


#在py的mysql db中，一旦创建了一个cursor，那么就默认创建了一个事务。
#直到提交事务为止，数据库的数据才会进行更改。但是对于不支持事务的数据库来说，事务不起作用。
"""
在计算机术语中是指访问并可能更新数据库中各种数据项的一个程序执行单元(unit)。在计算机术语中，事务通常就是指数据库事务。
一个数据库事务通常包含对数据库进行读或写的一个操作序列。它的存在包含有以下两个目的：

1、为数据库操作提供了一个从失败中恢复到正常状态的方法，同时提供了数据库即使在异常状态下仍能保持一致性的方法。
2、当多个应用程序在并发访问数据库时，可以在这些应用程序之间提供一个隔离方法，以防止彼此的操作互相干扰。

当一个事务被提交给了DBMS（数据库管理系统），则DBMS需要确保该事务中的所有操作都成功完成且其结果被永久保存在数据库中，
如果事务中有的操作没有成功完成，则事务中的所有操作都需要被回滚，回到事务执行前的状态（要么全执行，要么全都不执行）;
同时，该事务对数据库或者其他事务的执行无影响，所有的事务都好像在独立的运行
"""