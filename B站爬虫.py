from enum import Enum

import cchardet
import httpx
import qrcode
from httpx._models import Cookies
import re
import redis
import json
from pathlib import Path
import time
import asyncio
from typing import *
from lxml import etree
from threading import Thread
import pickle
import signal
from queue import Queue

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver import ChromeOptions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# from bilibili.Utils import FaildRetry, KuaiShiBie, check_attribute_is_matched, format_print_json, AsyncFaildRetry,FunctionalExtend
# from bilibili.Utils import extend_redis


from Utils import FaildRetry, KuaiShiBie, check_attribute_is_matched, format_print_json, AsyncFaildRetry,FunctionalExtend
from Utils import extend_redis


import django
class BilibiliSpider:
    chorme_path = r'F:\Software\chormedriver_win64\chormedriver.exe'
    urls={
        'main':r'https://www.bilibili.com/', # 主页地址
        'login':{
            'main':r'https://passport.bilibili.com/login',
            'qrcode_info':r'https://passport.bilibili.com/qrcode/getLoginUrl', # 获取qrcode相关信息的地址
            'login_info':r'https://passport.bilibili.com/qrcode/getLoginInfo' # 获取当前是否登录成功并且返回相关信息
        },
        'search':{
            'url':r'https://search.bilibili.com/{}?keyword={}&page={}', # 搜索的地址,
            'mapping':{
                'animate':{
                    'url_tag':'bangumi',
                    'xpath':r'//li[contains(@class,"bangumi-item")]/div/a',
                    'ch_name':'番剧',
                    'tag':'A'
                },
                'movie':{
                    'url_tag':'pgc',
                    'xpath':r'//li[contains(@class,"pgc-item")]/div/a',
                    'ch_name':'电影',
                    'tag':'B'
                },
                'video':{
                    'url_tag':'video',
                    'xpath':r'//li[contains(@class,"video-item")]/a',
                    'ch_name':'视频',
                    'tag':'C'
                }
            }
        },
        'video':{
            'type':{
                'A':'animate',
                'B':'movie',
                'C':'video'
            }
        }
    }

    class VideoType(Enum):
        ANIMATE = 'animate'
        MOVIE = 'movie'
        VIDEO = 'video'

    def __init__(self,username=None,password=None,phone=None):
        self.cookies = None # 保留cookies
        self.username,self.password,self.phone=username,password,phone
        self.search_cache = redis.Redis(host='127.0.0.1', port=6379,db=6,decode_responses=True)
        self.now_search_result = None
        self.save_path = Path("./bilibili_download") # 懒得写成配置了，每次启动都输入一次算了
        if not self.save_path.exists():
            self.save_path.mkdir()
        self.downloaded_urls_path = Path(".downloaded")
        self.downloaded_urls_dict = pickle.load(self.downloaded_urls_path.open('rb')) if self.downloaded_urls_path.exists() else {}
        print(self.downloaded_urls_dict)
        pass


    def set_save_path(self,path:str):
        if Path(path).exists():
            self.save_path = Path(path)
        pass


    def search_by_condition(self,tag:VideoType,keyword:str,page:int=1)->dict:
        search_result = {
            'count':0,
            'page':page,
            'max_page':page,
            'data':[]
        }
        search_resp = FaildRetry()(lambda: httpx.get(
            self.urls['search']['url'].format(
                self.urls['search']['mapping'][tag.value]['url_tag'],
                keyword,
                page
            ),
            cookies=self.cookies))()
        if search_resp.status_code != 200:
            print('搜索出错，请重新搜索')
            return
        # 自动识别编码
        search_chardet = cchardet.detect(search_resp.content)
        search_resp.encoding = search_chardet['encoding']
        # 初始化xpath对象
        search_result_data = etree.HTML(search_resp.text)
        list_data = search_result_data.xpath(self.urls['search']['mapping'][tag.value]['xpath'])
        search_result['count']=list_data.__len__()
        if search_result['count'] > 0:
            for index, item_data in enumerate(list_data):
                search_result['data'].append({
                    'title':item_data.attrib["title"],
                    'url':item_data.attrib["href"] if item_data.attrib["href"].startswith('http') else 'https:'+item_data.attrib["href"]
                })
        # 如果查找为空，则设为1
        try:
            search_result['max_page'] = int(search_result_data.xpath(
                r'(//button[contains(@class,"num-btn")]/text())[last()]')[0])
        except IndexError:
            search_result['max_page'] = 1
        except Exception as e:
            print(f'xpath执行错误，错误信息为：{e.with_traceback()}')
        return search_result


    def search_video(self,keywords:str,page:int = 1,research_if_exist=True)->dict:
        # 如果research_if_exist为假，并且缓存中有的话
        has = not research_if_exist and self.search_cache.get(f'{page},{keywords}')
        if has:
            search_dict = self.search_cache[f'{page},{keywords}']
        else:
            search_dict = {
                "animate": None,
                "movie": None,
                "video": None
            }
        # 因为这里顶多搜三次，所以不用异步或多线程了
        for name,values in self.urls['search']['mapping'].items():
            if not has:
                search_dict[name]=self.search_by_condition(self.VideoType(name),keywords,page)
            print(f'{values["tag"]}【{values["ch_name"]}】搜索结果数({search_dict[name]["page"]}/{search_dict[name]["max_page"]}页) {search_dict[name]["count"]}个结果')
            for result_index,result in enumerate(search_dict[name]['data']):
                print(f'\t{result_index+1}.{result["title"]}')
            pass
        if not has:
            self.search_cache[f'{page},{keywords}']=search_dict
        return search_dict

    def download_videos(self,video_type:str,video_num:int):
        try:
            video_url_dict = self.now_search_result[self.urls['video']['type'][video_type]]['data'][video_num-1]
            print(video_url_dict)
        except:
            print('该视频编号不存在')
            return 1
        video_info_html_resp = FaildRetry()(lambda :httpx.get(video_url_dict['url']))()
        if video_info_html_resp.status_code!=200:
            print('视频页面无法请求')
            return 2
        # 自动识别编码
        video_info_html_chardet = cchardet.detect(video_info_html_resp.content)
        video_info_html_resp.encoding = video_info_html_chardet['encoding']
        # 获取视频的BV号
        video_re_search = re.search(r'[/\\]+([^/\\]+?)([\?]|$)',video_url_dict['url'])
        video_id = video_re_search.group(1)
        # 获取视频详情json
        video_info_json_re_search_result = re.search(r'window\.__playinfo__=(\{.*?\})\s*</script>',video_info_html_resp.text)
        if video_info_json_re_search_result is None:
            print('无法找到视频信息，可能未登录或者该账号本来就无法获取到该视频的观看权限。')
            return 3
        video_info_json = json.loads(video_info_json_re_search_result.group(1))
        Path('B站json.json').write_text(format_print_json(video_info_json,_print=False),encoding='utf-8-sig')
        # 可以下载的视频清晰度
        accept_format_list = video_info_json['data']['accept_format'].split(',')
        accept_dict = {item['new_description']:item for item in video_info_json['data']['support_formats']}
        # 并不是所有清晰度都能直接下载，有的清晰度需要登录会员账号才可以获取到对应链接
        # 获取到大会员才能看的清晰度
        can_watch_quality_list=[]
        for video_item in video_info_json['data']['dash']['video']:
            can_watch_quality_list.append(video_item['id'])
        dahuiyuan_quality_set = set(video_info_json['data']['accept_quality']) ^ set(can_watch_quality_list)
        # 提醒用户选择
        print('请输入您想下载的视频的清晰度')
        for i in range(accept_format_list.__len__()):
            print(f'\t{i+1}.{video_info_json["data"]["accept_description"][i]}{"(需要登录大会员账号才可下载)" if video_info_json["data"]["accept_quality"][i] in dahuiyuan_quality_set else ""}')
        quality_select = input('直接回车或者错误输入视为可以下载的最高清晰度')
        try:
            quality_select = int(quality_select) - 1
            if quality_select<0 or quality_select>=accept_format_list.__len__() or quality_select not in can_watch_quality_list:
                quality_select = can_watch_quality_list[0]
        except:
            quality_select = 0
        # video组里有双倍的数据，猜测可能是备份链接。只使用偶数组链接吧
        video_target_obj = video_info_json['data']['dash']['video'][can_watch_quality_list.index(quality_select)]
        video_urls = FunctionalExtend([video_target_obj['baseUrl'],video_target_obj['base_url']])\
            .extend(video_target_obj['backupUrl'])\
            .extend(video_target_obj['backup_url']).raw
        video_init_range = video_target_obj['SegmentBase']['Initialization']
        # audio组貌似永远使用30280组，也就是最高级音频的组合
        audio_target_obj = video_info_json['data']['dash']['audio'][0]
        audio_urls = FunctionalExtend([audio_target_obj['baseUrl'],audio_target_obj['base_url']])\
            .extend(audio_target_obj['backupUrl'])\
            .extend(audio_target_obj['backup_url']).raw
        audio_init_range = audio_target_obj['SegmentBase']['Initialization']
        # 提供video链接列表和audio链接列表来进行下载。尝试使用异步下载
        loop = asyncio.get_event_loop()
        # 调用异步下载函数
        loop.run_until_complete(
            self.async_download_video(f'{video_id}_{quality_select}',video_urls,video_init_range,audio_urls,audio_init_range,video_url_dict['url'])
        )



        pass

    @staticmethod
    def async_write_file(queue:Queue,dowloaded_urls_dict:dict,fps:Tuple,config_path,all_config_dict)->None:
        """
            多线程中调用的写文件
            监控队列里的数据，取出写入对应文件
        :param queue: 异步结果队列
        :param dowloaded_urls_dict: 下载信息字典
        :param fps: 视频文件和音频文件流组成的Tuple
        :return: 无
        """
        tag_map=["视频","音频"]
        config_fp = config_path.open('wb')
        while not dowloaded_urls_dict['isfinish']:
            start_range, range_length, content, typeid = queue.get()
            FunctionalExtend(fps[typeid]).seek(start_range,0).write(content).flush()
            dowloaded_urls_dict['finish'][typeid]+=range_length
            dowloaded_urls_dict['audio' if typeid else 'video'].append(start_range)
            with config_path.open('wb') as config_fp:
                pickle.dump(all_config_dict,config_fp)
            print(f'{tag_map[typeid]}进度{dowloaded_urls_dict["finish"][typeid]/dowloaded_urls_dict["length"][typeid]*100}%')
            pass

    async def async_download_video(self,video_id:str ,video_urls:List[str], video_init_range:str, audio_urls:List[str], audio_init_range:str,referer:str):
        """
            异步下载视频
            video和audio列表里内容都是一样的，只是以防某些url失效
        :param video_id:
        :param video_urls:
        :param video_init_range:
        :param audio_urls:
        :param audio_init_range:
        :param referer: 链接来源
        :return:
        """
        # 查询读取是否有下载一半的文件
        now_dowloaded_urls_dict = {
            'video':[],
            'audio':[],
            'length':[0,0],
            'finish':[0,0],
            'isfinish':False
        }
        video_true_range,video_length,video_fp = self.init_download_file(video_id,typeid=0,urls=video_urls,range=video_init_range,referer=referer)
        audio_true_range,audio_length,audio_fp = self.init_download_file(video_id,typeid=1,urls=audio_urls,range=audio_init_range,referer=referer)
        # 先设置初始值
        now_dowloaded_urls_dict['finish'][0] = video_true_range
        now_dowloaded_urls_dict['finish'][1] = audio_true_range
        now_dowloaded_urls_dict['length'][0] = video_length
        now_dowloaded_urls_dict['length'][1] = audio_length
        # 如果存在那么覆盖
        if video_id in self.downloaded_urls_dict.keys():
            now_dowloaded_urls_dict = self.downloaded_urls_dict[video_id]
        self.downloaded_urls_dict[video_id] = now_dowloaded_urls_dict
        result_queue = Queue()
        # 异步下载的回调函数
        callback = lambda future:result_queue.put(future.result())
        #  启动多线程文件写入程序
        Thread(target=self.async_write_file,args=(result_queue,now_dowloaded_urls_dict,(video_fp,audio_fp),self.downloaded_urls_path,self.downloaded_urls_dict)).start()
        async with httpx.AsyncClient() as client:
            # 对文件流进行range分段。range长度以5120为长度
            task_list = []
            for start_range in range(video_true_range,video_length,5120):
                if start_range in now_dowloaded_urls_dict['video']:
                    continue
                task_list.append(FunctionalExtend(asyncio.ensure_future(self.async_download_slice_file(client,start_range,5120,video_urls,referer,0))).add_done_callback(callback).raw)
            for start_range in range(audio_true_range,audio_length,5120):
                if (start_range,5120) in now_dowloaded_urls_dict['audio']:
                    continue
                task_list.append(FunctionalExtend(asyncio.ensure_future(self.async_download_slice_file(client, start_range, 5120, audio_urls, referer,1))).add_done_callback(callback).raw)
                pass
            fus = await asyncio.wait(task_list)
            now_dowloaded_urls_dict['isfinish']=True


        pass

    def init_download_file(self, video_id:str, typeid, urls,range,referer):
        """
            根据视频名字和要保存的类型来初始化文件
        :param video_id: 视频名
        :param typeid: 0是视频，1是音频
        :param urls: 链接列表
        :param range: 初始化的测试range
        :param referer: 链接来源
        :return: 元祖（range长度，文件大小，文件流对象）
        """
        for url in urls:
            file_resp = FaildRetry(2,include_status=[200,206])(lambda :httpx.get(url,headers={'referer':referer,'range':f'bytes={range}','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 OPR/74.0.3911.107'},timeout=120))()
            # 如果请求失败的话用其他备用链接
            if not file_resp or file_resp.status_code not in [200,206]:
                continue
            # 获取真正的文件长度
            file_length = int(file_resp.headers['Content-Range'].split('/')[-1])
            true_range_length = int(file_resp.headers['Content-Length'])
            file_path = Path(self.save_path)/f'{video_id}_{typeid}.m4s'
            print(file_path.absolute())
            if file_path.exists():
                return true_range_length,file_length,file_path.open('wb')
            file_stream = file_path.open('wb')
            file_stream.write(file_resp.content)
            file_stream.write(b'\x00'*(file_length-true_range_length))
            return true_range_length,file_length,file_stream


        pass

    async def async_download_slice_file(self,client:httpx.AsyncClient, start_range:int,range_length:int,urls:List[str],referer:str,typeid:int):
        """
            下载的核心函数，异步的下载调用的函数
            range请求，请求完返回数据
        :param client: httpx的异步client
        :param start_range: 开始起点
        :param range_length: 最大步长
        :param urls: 链接列表
        :param referer: 引用
        :param typeid: 是视频还是音频
        :return:
        """
        for _ in range(60):
            for url in urls:
                resp = await AsyncFaildRetry(retry_counts=2, include_status=[200, 206])(lambda: client.get(url,headers={'referer': referer,'range': f'bytes={start_range}-{start_range + range_length}','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 OPR/74.0.3911.107'},timeout=60))()
                if not resp or resp.status_code not in [200, 206]:
                    continue
                return (start_range, int(resp.headers['Content-Length']), resp.content, typeid)

    def main(self):
        print('********欢迎来到Bilibili爬虫系统********')
        while True:
            main1_select = input("""您可以选择以下指令来进行相应的操作
    1.登陆（此操作不是必须，但是不登录会员账号的话需要会员才能观看的视频会搜不到）
    2.搜索视频
    3.退出系统
    错误输入或直接回车的话会被默认为退出系统
>>>""")
            if not main1_select.isalnum() or int(main1_select) not in [1, 2, 3]:
                main1_select = 3
            else:
                main1_select = int(main1_select)
            if main1_select == 1:
                self.main_login()
            elif main1_select == 2:
                self.main_search()
            else:
                return
            pass
        pass

    def main_login(self):
        main2_select = input("""您可以选择以下方式进行登录
    0.扫码登录
    1.密码登录
    2.短信登录
    错误输入和默认是扫码登录
>>>""")
        result = self.login(main2_select)
        if result is None:
            print('登录失败')
            return 1
        else:
            print('登录成功')
            return 0

    def main_search(self):
        while True:
            keywords = input("""请输入您要搜索的关键字或者输入exit退出搜索：""")
            if not keywords.strip():
                print('请输入非空关键字')
                continue
            if keywords.strip().lower()=='exit':
                return
            page = input("""请输入要查询的页数(直接回车默认第一页)：""")
            try:
                page = float(page)
                if page < 2:
                    page = 1
                else:
                    page = int(page)
            except:
                page = 1
            use_cache = input("""是否启动缓存？0否1是，默认启动：""")
            try:
                use_cache = bool(int(float(use_cache)))
            except:
                use_cache = True
            self.now_search_result = self.search_video(keywords, page, use_cache)
            main2_select2 = input("""请选择接下来的步骤：
    1.重新搜索
    2.设置视频保存路径
    3.退出该页面
    或输入A1，B1，C3这种类似的组合来下载指定视频。错误输入默认退出该页面。
>>>""")
            main2_select2 = main2_select2.upper()
            try:
                main2_select2 = int(main2_select2)
            except:
                try:
                    video_flag = main2_select2[0]
                    video_num = int(main2_select2[1:])
                except:
                    main2_select2 = 3
            if main2_select2 == 1:
                continue
            elif main2_select2 == 2:
                self.set_save_path(input("请输入要保存视频的路径："))
            elif main2_select2 == 3:
                print('退出搜索页面')
                return
            else:
                self.download_videos(video_flag, video_num)
                pass

    def login(self, type) -> Cookies:
        """
            0为扫码登录，1为账号密码登录，2为短信登陆
            数字取整，错误输入被认为扫码登录
            小于1的都是0
            大于等于2的都是2
        :return: cookies
        """
        try:
            type = float(type)
        except:
            type = 0
        if type < 1:
            type = 0
        elif type < 2:
            type = 1
        else:
            type = 2
        return getattr(self, f'_login_{type}')()

    def _login_0(self) -> Cookies:
        """
            扫码登录
        :return: 登陆后产生的Cookies
        """
        # 获取构建二维码用的相关信息
        qrcode_url_resp = FaildRetry()(lambda: httpx.get(self.urls['login']['qrcode_info']))()
        if qrcode_url_resp.status_code != 200:
            print(r'二维码获取失败...')
            return
        qrcode_url_json = qrcode_url_resp.json()
        oauthKey = qrcode_url_json['data']['oauthKey']
        qrcode_url = qrcode_url_json['data']['url']
        qr = qrcode.QRCode(version=3)
        qr.add_data(qrcode_url)
        qr.make()
        img = qr.make_image()
        img.show()
        # 开始心跳获取
        while True:
            time.sleep(1)
            getLoginInfo_resp = FaildRetry()(
                lambda: httpx.post(self.urls['login']['login_info'], data={
                    'oauthKey': oauthKey,
                    'gourl': self.urls['main']
                }))()
            if getLoginInfo_resp.status_code != 200:
                continue
            getLoginInfo_json = getLoginInfo_resp.json()
            if not getLoginInfo_json['status']:
                continue
            self.cookies = getLoginInfo_resp.cookies
            break
        print(f'登陆成功')
        return self.cookies

    def _login_1(self) -> Cookies:
        """
            账号密码登陆。
        :return:
        """
        chrome_options = ChromeOptions()
        chrome_options.headless = True
        chorme = webdriver.Chrome(options=chrome_options)
        chorme.get(self.urls['login']['main'])
        wait = WebDriverWait(chorme, 30, 0.2)
        # 获取现在是密码登录还是短信登录
        login_tabs = wait.until(lambda x: x.find_element_by_class_name('type-tab'))
        active_tab = wait.until(lambda x: x.find_element_by_class_name('active'))

        if active_tab.text == '短信登录':
            login_tabs.find_elements_by_tag_name('span')[0].click()
        # 填写用户名和密码
        chorme.find_element_by_id('login-username').send_keys(self.username or input('请输入您的用户名：'))
        chorme.find_element_by_id('login-passwd').send_keys(self.password or input('请输入您的密码：'))
        # 这层是因为B站验证码错一次之后偶尔如果不关再次识别的话即使对了也是错的，所以重新来
        geetest_img_url = ""
        while True:
            # 点击登陆按钮触发验证
            # btn_login = wait.until(lambda x:x.find_element_by_class_name('btn-login'))
            # btn_login.click()
            btn_login_element = chorme.find_element_by_class_name('btn-login')
            webdriver.ActionChains(chorme).move_to_element(btn_login_element).click(btn_login_element).perform()
            # 发送给快识别验证码平台
            # 这层循环是可能的循环多次进行验证
            while True:
                # 获取验证码图片,等待图片的src属性出现
                wait.until(
                    check_attribute_is_matched((By.CLASS_NAME, 'geetest_item_img'), 'src', 'http')
                )
                # 等待验证码图片刷新
                geetest_img = chorme.find_element_by_class_name('geetest_item_img')
                if geetest_img_url == geetest_img.get_attribute('src') or geetest_img.get_attribute('src') == '':
                    continue
                geetest_img_url = geetest_img.get_attribute('src')
                result = KuaiShiBie.yanzhengma(geetest_img_url)
                if result['code'] == 1:
                    print(result['msg'])
                    return
                elif result['code'] == 2:  # 识别失败就回报错误并且刷新重新识别
                    print(result['msg'])
                    chorme.find_element_by_class_name('geetest_refresh').click()
                    KuaiShiBie.yanzhengma_error_report(result['id'])
                    continue
                break
            # 因为图片大小和实际不一样，所以坐标需要放缩
            rate = geetest_img.size['width'] / result['width']
            for x, y in result['data']:
                x *= rate
                y *= rate
                ActionChains(chorme).move_to_element_with_offset(geetest_img, x, y).click().perform()
            # 清空提示
            chorme.execute_script('$(".geetest_result_tip").text("")')
            chorme.find_element_by_class_name('geetest_commit_tip').click()
            try:
                # 等待出现“验证成功”或者“验证失败”
                wait.until(EC.text_to_be_present_in_element((By.CLASS_NAME, 'geetest_result_tip'), '验证'))
                result = chorme.find_element_by_class_name('geetest_result_tip').text
                if result == '验证成功':
                    break
            except NoSuchElementException as e:
                break
            pass
        self.cookies = Cookies({item['name']: item['value'] for item in chorme.get_cookies()})
        return self.cookies

    def _login_2(self) -> Cookies:
        """
            手机号登陆。
        :return:
        """
        chrome_options = ChromeOptions()
        chrome_options.headless = True
        chorme = webdriver.Chrome(options=chrome_options)
        chorme.get(self.urls['login']['main'])
        wait = WebDriverWait(chorme, 30, 0.2)
        # 获取现在是密码登录还是短信登录
        login_tabs = wait.until(lambda x: x.find_element_by_class_name('type-tab'))
        active_tab = wait.until(lambda x: x.find_element_by_class_name('active'))

        if active_tab.text == '密码登录':
            login_tabs.find_elements_by_tag_name('span')[1].click()
        # 填写用户名和密码
        chorme.find_element_by_xpath(r'//input[@placeholder="填写常用手机号"]').send_keys(
            self.phone or input('请输入您的常用手机号：'))

        geetest_img_url = ""
        while True:
            WebDriverWait(chorme, 61).until(
                EC.text_to_be_present_in_element(
                    (By.XPATH, r'//button[contains(@class,"el-button--primary")]/span'), '验证码')
            )
            # 点击登陆按钮触发验证
            chorme.find_element_by_class_name('el-button--primary').click()
            # 发送给快识别验证码平台
            # 这层循环是可能的循环多次进行验证
            while True:
                # 获取验证码图片,等待图片的src属性出现
                wait.until(
                    check_attribute_is_matched((By.CLASS_NAME, 'geetest_item_img'), 'src', 'http')
                )
                geetest_img = chorme.find_element_by_class_name('geetest_item_img')
                if geetest_img_url == geetest_img.get_attribute('src') or geetest_img.get_attribute('src') == '':
                    continue
                geetest_img_url = geetest_img.get_attribute('src')
                result = KuaiShiBie.yanzhengma(geetest_img_url)
                if result['code'] == 1:
                    print(result['msg'])
                    return
                elif result['code'] == 2:  # 识别失败就回报错误并且刷新重新识别
                    print(result['msg'])
                    chorme.find_element_by_class_name('geetest_refresh').click()
                    KuaiShiBie.yanzhengma_error_report(result['id'])
                    continue
                break
            # 因为图片大小和实际不一样，所以坐标需要放缩
            rate = geetest_img.size['width'] / result['width']
            for x, y in result['data']:
                x *= rate
                y *= rate
                ActionChains(chorme).move_to_element_with_offset(geetest_img, x, y).click().perform()
            # 清空提示
            chorme.execute_script('$(".geetest_result_tip").text("")')
            chorme.find_element_by_class_name('geetest_commit_tip').click()
            try:
                # 等待出现“验证成功”或者“验证失败”
                wait.until(EC.text_to_be_present_in_element((By.CLASS_NAME, 'geetest_result_tip'), '验证'))
                result = chorme.find_element_by_class_name('geetest_result_tip').text
                print(result)
                if result == '验证失败':
                    # 验证失败，关闭验证码重新验证
                    chorme.find_element_by_class_name('geetest_close').click()
                    continue
            except NoSuchElementException as e:
                # 意外错误比如说断网的话重新验证
                continue

            def is_login_success(driver) -> Union[str, bool]:
                """
                    复杂的是否成功登陆的判断
                :param driver:
                :return: ok或no或都不满足
                """
                try:
                    flag1 = 'no' if driver.find_element_by_xpath(
                        r'//*[@id="geetest-wrap"]/div/div[3]/div[4]/p').text == '验证码错误' else False
                    try:
                        flag2 = driver.find_element_by_class_name('btn-login')
                        flag2 = False
                    except StaleElementReferenceException:
                        flag2 = 'ok'
                except:
                    flag1 = False
                    flag2 = 'ok'
                return flag1 or flag2

            want_to_again = False
            while True:
                chorme.find_element_by_xpath(r'//input[@placeholder="请输入短信验证码"]').send_keys(input('请输入短信验证码：'))
                chorme.find_element_by_class_name('btn-login').click()

                result = wait.until(is_login_success)
                # no是验证码错误，yes是验证码正确，登陆成功
                if result == 'no':
                    want = input('您是想重新获取验证码还是重新输入？\n\t1.重新输入\n\t2.重新获取验证码')
                    if want == '2':
                        print('请等待验证码……')
                        want_to_again = True
                        break
                    else:
                        continue
                else:
                    break
                pass
            if want_to_again:
                continue
            break

            pass

        self.cookies = Cookies({item['name']: item['value'] for item in chorme.get_cookies()})
        return self.cookies

    def __del__(self):
        print(f'保存数据')
        with self.downloaded_urls_path.open('wb') as fp:
            pickle.dump(self.downloaded_urls_dict,fp)

if __name__ == '__main__':
    bilibili = BilibiliSpider()

    def my_exit(signum,frame):
        print('成功退出')
        import os
        os._exit(0)
        pass
    signal.signal(signal.SIGINT,my_exit)
    signal.signal(signal.SIGTERM,my_exit)

    bilibili.main()



