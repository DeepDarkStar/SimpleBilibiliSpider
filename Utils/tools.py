import asyncio
import time
from typing import *
from types import FunctionType,LambdaType,MethodType,BuiltinFunctionType,BuiltinMethodType
import re

def FaildRetry(retry_counts = 10,include_status=[200],error_status=[],sleep_time=1):
    """
        当error_status是空或None时，只要不满足include里的status都会重新调用请求
        当不为None或空时，不满足include且满足error_status时才重新请求
    :param retry_counts: 重试次数，默认10次
    :param include_status: 正确的请求码
    :param error_status: 错误的请求码
    :param sleep_time: 睡眠时间，单位秒
    :return: 装饰器装饰的请求函数，要求被装饰的函数返回response
    """
    def wrapper(func):
        def w_func(*args,**kwargs):
            count = retry_counts
            while count>=0:
                count-=1
                resp = func(*args,**kwargs)
                if error_status and (resp.status_code not in include_status and resp.status_code in error_status): # 如果error_status不为空，且不在正确，在错误列表里时，重新请求
                    time.sleep(sleep_time)
                    continue
                # 如果错误列表不存在，并且不在正确列表里，重新请求
                if not error_status and  resp.status_code not in include_status:
                    time.sleep(sleep_time)
                    continue
                return resp
        return w_func
    return wrapper

def AsyncFaildRetry(retry_counts = 10,include_status=[200],error_status=[],sleep_time=1):
    """
        FaildRetry的异步模式
        当error_status是空或None时，只要不满足include里的status都会重新调用请求
        当不为None或空时，不满足include且满足error_status时才重新请求
    :param retry_counts: 重试次数，默认10次
    :param include_status: 正确的请求码
    :param error_status: 错误的请求码
    :param sleep_time: 睡眠时间，单位秒
    :return: 装饰器装饰的请求函数，要求被装饰的函数返回response
    """
    def wrapper(func):
        async def w_func(*args,**kwargs):
            count = retry_counts
            while count>=0:
                count-=1
                try:
                    resp = await func(*args, **kwargs)
                except:
                    return None
                if error_status and (resp.status_code not in include_status and resp.status_code in error_status): # 如果error_status不为空，且不在正确，在错误列表里时，重新请求
                    await asyncio.sleep(sleep_time)
                    continue
                # 如果错误列表不存在，并且不在正确列表里，重新请求
                if not error_status and  resp.status_code not in include_status:
                    await asyncio.sleep(sleep_time)
                    continue
                return resp
        return w_func
    return wrapper


def check_attribute_is_matched(locate:Tuple,attr_name:str,attr_value:str,flag=re.I):
    """
        selenium中可以对指定locate处的元素的attr_name进行判断是否符合attr_value的规则，attr_value可以是正则字符串
    :param locate: 元素查找规则
    :param attr_name: 属性名
    :param attr_value: 属性值匹配规则
    :param flag: 默认re.I，忽略大小写
    :return: 匹配函数
    """
    def check(driver)->bool:
        try:
            true_attr_value = driver.find_element(*locate).get_attribute(attr_name).__str__()
        except:
            return False
        return re.search(attr_value,true_attr_value,flag) is not None
    return check
def format_print_json(obj:Union[dict,str,List],level = 0,_print=True):
    """
        格式化打印json对象
    :param obj: json对象
    :param level:
    :return:
    """
    import json
    single_char = '\''
    result_str_list = []
    format_print_str = lambda obj:f'"{repr(obj)[1:-1]}"' if isinstance(obj,str) else str(obj)
    def format_print_list(obj:List,llevel = 0,max_len=30):
        if len(str(obj))<max_len:
            result_str_list.extend(
                ('[',
                ', '.join([format_print_str(it) for it in obj]),
                ']')
            )
            return
        list_count = len(obj)
        count = 1
        result_str_list.append('[\n')
        for it in obj:
            result_str_list.append('\t' * (llevel + 1))
            if isinstance(it, dict):
                result_str_list.append(format_print_json(it, llevel + 1,_print=False))
            elif isinstance(it, (list, tuple, set, frozenset)):
                format_print_list(it, llevel + 1)
            else:
                result_str_list.append(format_print_str(it))
            if count<list_count:
                result_str_list.append(',\n')
            count += 1
        result_str_list.append('\n'+'\t'*llevel+']')
        pass
    if isinstance(obj,str):
        obj = json.loads(obj)
    elif isinstance(obj,(list,tuple,set,frozenset)):
        format_print_list(obj)
        if _print:
            print(''.join(result_str_list))
        return ''.join(result_str_list)
    if not obj:
        if _print:
            print(str(obj))
        return str(obj)
    result_str_list.append('{\n')
    item_counts = len(obj.keys())
    count = 1
    for k,v in obj.items():
        result_str_list.append('\t'*(level+1)+f'{format_print_str(k)}:')
        if isinstance(v,dict):
            result_str_list.append(format_print_json(v,level+1,_print=False))
        elif isinstance(v,(list,tuple,set,frozenset)):
            format_print_list(v,level+1)
        else:
            result_str_list.append(format_print_str(v))
        if count<item_counts:
            result_str_list.append(',\n')
        count+=1
        pass
    else:
        result_str_list.append('\n'+'\t'*level+'}')
    if _print:
        print(''.join(result_str_list))
    return ''.join(result_str_list)


class FunctionalExtend:
    """
        链式扩展类
        用这个包装类之后所有函数都是链式扩展类型了
        >>> obj = [1,2,3]
        >>> print(FunctionalExtend(obj).append(5).append(6).raw)
    """


    def __init__(self,obj):
        self.raw = obj
        self.last_result = None
    @staticmethod
    def warp_return_self(obj):
        def warp_func(func):
            def warp(*args,**kwargs):
                obj.last_result = func(*args,**kwargs)
                return obj
            return warp
        return warp_func
    def __getattr__(self, item):
        obj_attr = getattr(self.raw,item,None)
        if obj_attr:
            if isinstance(obj_attr,(FunctionType,LambdaType,MethodType,BuiltinFunctionType,BuiltinMethodType)):
                return self.warp_return_self(self)(obj_attr)
        return obj_attr
    def __repr__(self):
        return self.raw.__repr__()


class A:
    def func(self,arga:int):
        """
            这是Func函数
        :param arga: args对象
        :return: 返回空
        """
        print(f'func')
        pass

