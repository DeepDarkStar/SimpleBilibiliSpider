

import redis
import json
import datetime

from redis.client import CaseInsensitiveDict


def __extend_get(self, name, default=None):
    """
        扩展get，可以自动解析json字符串
        json.loads在转换数字字符串时不会出错，所以需要额外判断
    :return: 返回值
    """
    value = self.execute_command('GET', name)
    if value is None and default is not None:
        value = default
    if isinstance(value,str) and not value.isalnum():
        try:
            value = json.loads(value)
        except:
            pass
    return value



def __extend_set(self, name, value,
            ex=None, px=None, nx=False, xx=False, keepttl=False):
        """
        Set the value at key ``name`` to ``value``

        ``ex`` sets an expire flag on key ``name`` for ``ex`` seconds.

        ``px`` sets an expire flag on key ``name`` for ``px`` milliseconds.

        ``nx`` if set to True, set the value at key ``name`` to ``value`` only
            if it does not exist.

        ``xx`` if set to True, set the value at key ``name`` to ``value`` only
            if it already exists.

        ``keepttl`` if True, retain the time to live associated with the key.
            (Available since Redis 6.0)
        """
        if isinstance(value,dict):
            try:
                value = json.dumps(value)
            except:
                raise ValueError(f'该字典不能正确转换成json字符串：{value}')
        pieces = [name, value]
        if ex is not None:
            pieces.append('EX')
            if isinstance(ex, datetime.timedelta):
                ex = int(ex.total_seconds())
            pieces.append(ex)
        if px is not None:
            pieces.append('PX')
            if isinstance(px, datetime.timedelta):
                px = int(px.total_seconds() * 1000)
            pieces.append(px)

        if nx:
            pieces.append('NX')
        if xx:
            pieces.append('XX')

        if keepttl:
            pieces.append('KEEPTTL')

        return self.execute_command('SET', *pieces)

redis.Redis.get = __extend_get
redis.Redis.set = __extend_set