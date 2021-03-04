from typing import *
import httpx
import io
from PIL import Image
from .tools import FaildRetry
import base64

class KuaiShiBie:
    kuaishibie={
        'url':r'http://api.kuaishibie.cn/imageXYPlus',
        'error':r'http://api.kuaishibie.cn/reporterror.json',
        'username':'Dofs',
        'password':'1415926'
    }
    @classmethod
    def yanzhengma(cls,pic_ref:str,type:int=27)->dict:
        """
            快识别平台识别图片
        :param pic_ref: 图片地址
        :param type: 识别类型，默认27识别1-4个数字，更多类型查看http://www.kuaishibie.cn/docs/index.html?spm=null
        :return: 识别结果，错误返回数字
        """
        img = httpx.get(pic_ref,timeout=120).content
        img_data = Image.open(io.BytesIO(img))
        kuaishibie_resp = FaildRetry()(lambda :httpx.post(cls.kuaishibie['url'],headers={'Content-Type':'application/json;charset=UTF-8'},json={
            'username':cls.kuaishibie['username'],
            'password':cls.kuaishibie['password'],
            'typeid':27,
            'image':base64.b64encode(img).decode()
        },timeout=120))()
        if kuaishibie_resp.status_code!=200:
            return {'code':1,'msg':'验证码识别平台无法请求'}
        kuaishibie_json = kuaishibie_resp.json()
        if not kuaishibie_json['success']:
            return {'code':2,'msg':f'验证码识别失败，请进行其他请求。错误消息为：{kuaishibie_json["message"]}'}
        return {
            'code':0,
            'msg':'success',
            'id':kuaishibie_json['data']['id'],
            'data':[list(map(int,xy.split(','))) for xy in kuaishibie_json['data']['result'].split('|')],
            'width':img_data.width,
            'height':img_data.height
        }

    @classmethod
    def yanzhengma_error_report(cls,id)->int:
        """
            快识别的报错接口
        :param id: 错误ID
        :return: 1,2是错误，0正确
        """
        error_resp = FaildRetry()(lambda :httpx.post(cls.kuaishibie['error'],data={'id':id}))()
        if error_resp.status_code!=200:
            print(f'请求回报失败，错误ID为：{id}')
            return 1
        error_json = error_resp.json()
        if error_json['success']:
            return 0
        print(f'请求回报出错，错误消息为：{error_json["message"]}')
        return 2