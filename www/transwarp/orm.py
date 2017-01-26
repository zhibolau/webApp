#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Zhibo Liu'

"""
orm模块设计的原因：
    1. 简化操作
        sql操作的数据是 关系型数据， 而python操作的是对象，为了简化编程 所以需要对他们进行映射
        映射关系为：
            表 ==>  类 表中所有data
            行 ==> 实例  表中的一行data
设计orm接口：
    1. 设计原则：
        根据上层调用者设计简单易用的API接口
    2. 设计调用接口
        1. 表 <==> 类
            通过类的属性 来映射表的属性（表名，字段名， 字段属性） 字段名就是每列的名字, 字段属性是该列是int 还是str etc...
                from transwarp.orm import Model, StringField, IntegerField
                class User(Model):
                    __table__ = 'users'
                    id = IntegerField(primary_key=True)
                    name = StringField()
            从中可以看出 __table__ 拥有映射表名， id/name 用于映射 字段对象（字段名 和 字段属性）
        2. 行 <==> 实例
            通过实例的属性 来映射 行的值
                # 创建实例:
                user = User(id=123, name='Michael')
                # 存入数据库:
                user.insert()
            最后 id/name 要变成 user实例的属性
"""

#处理字段属性
class Field(object):
    """
        保存数据库中的表的  字段属性
        _count: 类属性，每实例化一次就+1
        self._order: 实例属性， 实例化时从类属性处得到，用于记录 该实例是 该类的第多少个实例
            例如最后的doctest：
                定义user时该类进行了5次实例化，来保存字段属性
                    id = IntegerField(primary_key=True)
                    name = StringField()
                    email = StringField(updatable=False)
                    passwd = StringField(default=lambda: '******')
                    last_modified = FloatField()
                最后各实例的_order 属性就是这样的
                    INFO:root:[TEST _COUNT] name => 1
                    INFO:root:[TEST _COUNT] passwd => 3
                    INFO:root:[TEST _COUNT] id => 0
                    INFO:root:[TEST _COUNT] last_modified => 4
                    INFO:root:[TEST _COUNT] email => 2
                最后生成__sql时（见_gen_sql 函数），这些字段就是按序排列
                    create table `user` (
                    `id` bigint not null,
                    `name` varchar(255) not null,
                    `email` varchar(255) not null,
                    `passwd` varchar(255) not null,
                    `last_modified` real not null,
                    primary key(`id`)
                    );
    """
    _count = 0 #每实例化一次就加1
    def __init__(self, **kwargs):

        #根据下边定义的各个Field kwargs应该是包含有所有字段名字的字典
        #所以才可以把不对应的都设置成各自Field所对应的属性
        #The method get() returns a value for the given key. If key is not available then returns default value None.
        #kwargs 是字典
        self.name = kwargs.get('name', None) #第二个参数是默认值
        self._default = kwargs.get('default', None)
        self.primary_key = kwargs.get('primary_key', None)
        self.nullable = kwargs.get('nullable', None)
        self.updatable = kwargs.get('updatable', None)
        self.insertable = kwargs.get('insertable', None)
        self.ddl = kwargs.get('ddl', None) #实例ddl属性：实例default信息，3中标志位：N U I
        self._order = Field._count
        Field._count +=1

    @property #可以让方法变成属性
    def default(self):
        """
        利用getter实现的一个写保护的 实例属性

        self._default: 用于让orm自己填入缺省值，缺省值可以是 可调用对象，比如函数
                    比如：passwd 字段 <StringField:passwd,varchar(255),default(<function <lambda> at 0x0000000002A13898>),UI>
                         这里passwd的默认值 就可以通过 返回的函数 调用取得
        其他的实例属性都是用来描述字段属性的
        """
        d = self._default
        return d() if callable(d) else d
        '''猜测
        if callable(d):
            return d()
        说明 d是可以被调用的, d可以是函数, 所以 要return d()
        '''

    def __str__(self):
        """
               返回 实例对象 的描述信息，比如：
                   <IntegerField:id,bigint,default(0),UI>
                   类：实例：实例ddl属性：实例default信息，3种标志位：N U I
        """
        s = ['<%s:%s,%s,default(%s),' % (self.__class__.__name__, self.name, self.ddl, self._default)]
        self.nullable and s.append('N')
        self.updatable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')
        '''
            >>> s = 'sdf'
            >>> ''.join(s)
            'sdf'
            >>> '3'.join(s)
            's3d3f'
        '''
        return ''.join(s)

class StringField(Field):
    """
        保存String类型字段的属性
    """
    def __init__(self, **kwargs):
        if not 'default' in kwargs:
            kwargs['default'] = ''
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'varchar(255)'
        super(StringField, self).__init__(**kwargs)
        '''
        对于super(B, self).__init__()是这样理解的：super(B, self)首先找到B的父类（就是类A），
        然后把类B的对象self转换为类A的对象，然后“被转换”的类A对象调用自己的__init__函数。
        '''

class IntegerField(Field):
    def __init__(self, **kwargs):
        if not 'default' in kwargs:
            kwargs['default'] = 0
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'bigint'
        super(IntegerField, self).__init__(**kwargs)

class FloatField(Field):
    def __init__(self, **kwargs):
        if not 'default' in kwargs:
            kwargs['default'] = 0.0
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'real'
        super(FloatField, self).__init__(**kwargs)

class BooleanField(Field):
    def __init__(self, **kwargs):
        if not 'default' in kwargs:
            kwargs['default'] = False
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'bool'
        super(BooleanField, self).__init__(**kwargs)

class TextField(Field):
    def __init__(self, **kwargs):
        if not 'default' in kwargs:
            kwargs['default'] = ''
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'text'
        super(TextField, self).__init__(**kwargs)

class BlobField(Field):
    def __init__(self, **kwargs):
        if not 'default' in kwargs:
            kwargs['default'] = ''
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'blob'
        super(BlobField, self).__init__(**kwargs)

class VersionField(Field):
    def __init__(self, name=None):
        super(VersionField, self).__init__(name = name, default=0, ddl='bigint')

#??????????????????????????? 干屁用的!!!!!!!!!!???
_triggers = frozenset(['pre_insert','pre_update', 'pre_delete'])

def _gen_sql(table_name, mappings):
    """
        类 ==>(映射/转换成) 表时 生成创建表的sql
    """
    pk = None
    sql = ['-- _gen_Sql is generating SQL for %s: ' % table_name, 'create table `%s` (' %table_name]
    for f in sorted(mappings.values(), lambda x, y: cmp(x._order, y._order)):#用的是Field中_order来排序的
        '''self._order: 实例属性， 实例化时从类属性处得到，用于记录 该实例是 该类的第多少个实例
            例如最后的doctest：
                定义user时该类进行了5次实例化，来保存字段属性
                    id = IntegerField(primary_key=True)
                    name = StringField()
                    email = StringField(updatable=False)
                    passwd = StringField(default=lambda: '******')
                    last_modified = FloatField()
                最后各实例的_order 属性就是这样的
                    INFO:root:[TEST _COUNT] name => 1
                    INFO:root:[TEST _COUNT] passwd => 3
                    INFO:root:[TEST _COUNT] id => 0
                    INFO:root:[TEST _COUNT] last_modified => 4
                    INFO:root:[TEST _COUNT] email => 2
                最后生成__sql时（见_gen_sql 函数），这些字段就是按序排列
                    create table `user` (
                    `id` bigint not null,
                    `name` varchar(255) not null,
                    `email` varchar(255) not null,
                    `passwd` varchar(255) not null,
                    `last_modified` real not null,
                    primary key(`id`)
                    );
        '''
        if not hasattr(f,'ddl'):
            raise StandardError('no ddl in field "%s".' % f)
        ddl = f.ddl
        nullable = f.nullable
        if f.primary_key:
            pk = f.name  #此name为当前这个row的name   ?????????????????????为啥不用id呢????????????????????????
        #?????????????????????????????????????????????????
        sql.append(nullable and ' `%s` %s,' %(f.name, ddl) or ' `%s` %s not null,' % (f.name, ddl))
        # and or: python 从左至又看表达式 没有and比or优先级高一说
        #x or y: x若假 则return y, x真, return x
        #x and y: x若假 return x, x真 return y
        #nullable is False: return nullable, 最后 return ' `%s` %s not null,' % (f.name, ddl))
        #nullable is True: return ' `%s` %s,' %(f.name, ddl)----->真,return ' `%s` %s,' %(f.name, ddl)
        #                                                   ----->假,return ' `%s` %s not null,' % (f.name, ddl)
    sql.append(' primary key(`%s`)' % pk)
    sql.append(');')
    return '\n'.join(sql)


























