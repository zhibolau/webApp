#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import threading

import time
import uuid

import functools

__author__ = 'Zhibo Liu'

# db得先有 连接(惰性连接) 然后再处理sql语句(也就是用 事务)


class Dict(dict):
    '''
    实现一个简单的可以通过属性访问的字典，比如 x.key = value
    '''
    def __init__(self,names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k,v in zip(names, values):
            #zip([seql, ...])接受一系列可迭代对象作为参数，将对象中对应的元素打包成一个个tuple（元组），
            # 然后返回由这些tuples组成的list（列表）。若传入参数的长度不等，则返回list的长度和参数中长度最短的对象相同。
            '''
            >>> z1=[1,2,3]
            >>> z2=[4,5,6]
            >>> result=zip(z1,z2)
            >>> result  ---->  [(1, 4), (2, 5), (3, 6)]
            '''
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

#engine对象持有数据库连接
engine = None


class DBError(Exception):
    pass

class MultiColumnError(DBError):
    pass



'''
_xxx       不能用'from module import *'导入

__xxx__  系统定义名字

__xxx     类中的私有变量名

'''

class _Engine(object):#db 引擎对象
    def __init__(self,connect):
        self._connect = connect

    def connect(self):
        return self._connect()


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
    # 生成全局对象engine 持有db连接
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

class _TransactionCtx(object):
    # deal with db transactions
    """
       事务嵌套比Connection嵌套复杂一点，因为事务嵌套需要计数，
       每遇到一层嵌套就+1，离开一层嵌套就-1，最后到0时提交事务
    """
    def __enter__(self):
        global _db_ctx # threading.local obj
        self.should_close_conn = False #所有sql语句执行结束 就设置为true exit函数会用到
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.should_close_conn = True
        _db_ctx.transactions = _db_ctx.transactions+1
        logging.info('Transaction Starts! ' if _db_ctx.transactions ==1 else 'This sql will join current transaction....')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        '''
        __exit__()的参数中exc_type, exc_value, traceback用于描述异常。
        异常类型，异常值,异常追踪信息
        我们可以根据这三个参数进行相应的处理。如果正常运行结束，这三个参数都是None。
        '''
        global _db_ctx
        _db_ctx.transactions = _db_ctx.transactions - 1
        try:
            if _db_ctx.transactions==0:
                '''
                commit()方法执行游标的所有更新操作，rollback（）方法回滚当前游标的所有操作。每一个方法都开始了一个新的事务。
                '''
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
        finally:
            if self.should_close_conn:
                _db_ctx.cleanup()##清理连接对象 关闭连接   参照class找到cleanup

    def commit(self):
        global _db_ctx
        logging.info('Current transaction is being committed')
        try:
            _db_ctx.connection.commit()
            logging.info('Commit is successfully finished. ')
        except:
            logging.warning('Commit failed. Rollback the current commit.')
            _db_ctx.connection.rollback()
            logging.info('Rollback finished. __from commit() _TransactionCtx')
            raise

    def rollback(self):
        global _db_ctx
        logging.info('This is rollback func. I am rollbacking current transaction. ')
        _db_ctx.connection.rollback()
        logging.info('This is rollback func.Rollback finished. ')

def transaction():
    #实现事务功能
    return _TransactionCtx()

def with_transaction(func):
    #设计一个装饰器 替换with语法
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        _start = time.time()
        with _TransactionCtx():
            return func(*args, **kw)
        _profiling(_start)
    return _wrapper

def _select(sql, first, *args):  # first 代表是不是直选一个记录 得下有select_one  妈的应该用 one_record
    """
        执行SQL，返回一个结果 或者多个结果组成的列表
    """
    global _db_ctx
    cursor = None
    sql = sql.replace('?', '%s')
    # Python replace() 方法把字符串中的 old（旧字符串） 替换成 new(新字符串)，
    # 如果指定第三个参数max，则替换不超过 max 次。
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        if cursor.description:
            #cursor.description returns a list of tuples describing the columns in a result set
            #只用于select语句，返回一行的列名
            names = [x[0] for x in cursor.description] #拿到 每行的名字
        if first:
            values = cursor.fetchone()
            if not values:
                return None
            return Dict(names,values) #拿到所有数据 包括 名字与数值
        return [Dict(names,x) for x in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()

@with_connection
def select_one(sql, *args):
    """
      执行SQL 仅返回一个结果
      如果没有结果 返回None
      如果有1个结果，返回一个结果
      如果有多个结果，返回第一个结果
    """
    return _select(sql, True, *args)

@with_connection
def select_int(sql, *args):
    """
        执行一个sql 返回一个数值，
        注意仅一个数值，如果返回多个数值将触发异常
    """
    d = _select(sql, True, *args)
    if len(d) !=1:
        raise MultiColumnError('ONLY one column is expected! ')
    return d.values(0)

@with_connection
def select(sql, *args):
    """
        执行sql 以列表形式返回结果
        其实是 select_multi
    """
    return _select(sql, False, *args)

@with_connection
def _update(sql, *args):
    """
        执行update 语句，返回update的行数
    """
    global _db_ctx
    cursor = None
    sql = sql.replace('?', '%s')
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        r = cursor.rowcount
        if _db_ctx.transactions == 0:
            logging.info('There is no transaction environment. Auto commit is going to happen! ')
            _db_ctx.connection.commit()
        return r
    finally:
        if cursor:
            cursor.close()
def update(sql, *args):
    """
        执行update 语句，返回update的行数"""
    return _update(sql, *args)


def insert(table, **kw):
    cols, args = zip(*kw.iteritems())
    # why use *kw not **kw ???????????????????????????  反zip???? 猜对啦
    #zip()配合*号操作符,可以将已经zip过的列表对象解压
    #剖离出 col row对应的value 把什么什么插入到此表中的什么什么位置
    #反zip 就是把原dict中 key都放在一个list value放一list
    # cols =[key] list
    # args = [value] list
    sql = 'insert into `%s` (%s) values (%s)' %\
                      (table,
                             ','.join(['`%s`' % col for col in cols]),
                                        ','.join(['?' for i in range(len(cols))])) #此处? 在_update中会被替换成%s
    #大sql句子不好理解!!!!!!!!!!!!!!!!!!!!!!!!!
    return _update(sql, *args)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    create_engine('root', 'password', 'testWebApp')# test时候此database得存在
    update('drop table if exists user')
    update('create table user (id int primary key, name text, email text, password text, last_modified real)')
    import doctest
    doctest.testmod()






