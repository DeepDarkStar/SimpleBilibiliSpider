# SimpleBilibiliSpider
简易B站登陆和视频爬虫（未做完）
## 完成部分
1. 扫码登陆、账号密码登陆、短信登陆
2. 搜索视频，按页数搜索
3. 支持搜索缓存（这里用了redis，需要自己准备）
4. 视频下载，使用的异步下载
5. 下载时支持断点续传，退出之后重新下载会接着下
## 未完成部分
1. 番剧和电影的下载（实际上和视频的网页原理差不多，都是解析json，只不过格式不太一样）
2. 重新下载的选项（目前只支持自己重新搜索到对应视频并且选择进去）
3. 存结果到数据库
4. 将音频M4S和视频MS4合并成视频文件，这个原理是在代码里调用FFMPEG命令行即可，也不难(
