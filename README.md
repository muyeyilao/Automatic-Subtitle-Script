# B 站整句字幕

This is a real-time subtitle script that gives your Bilibili videos cinematic-style advance subtitles, and supports mouse control of position and size.

看 B 站普通视频时，把识别出的**整句话**显示在播放器底部。每条字幕从该句第一个字的时间开始显示，拖动进度条后也会自动同步。

## 原理与限制

要在第一个字出现时知道后面整句话，必须先拿到后续音频。因此首次打开一个视频时，扩展会暂停播放器，下载整段音频；开头约半分钟的语音转写完成后就开始播放，同时继续生成后面的字幕。如果播放追上了转写进度，播放器会短暂停下，等下一批字幕准备好再继续。同一个视频、同一个分 P 再次打开时会直接使用本地缓存。首次下载语音模型也需要一些时间和磁盘空间；CPU 转写长课仍可能较慢。字幕是机器识别的，可能有错字或时间偏差。当前支持 `www.bilibili.com/video/BV...` 和 `.../av...` 的普通视频页，不支持直播、番剧或课堂专区的其他页面。

## 安装（Windows）

1. 双击 [启动字幕.cmd](启动字幕.cmd)。它会在首次启动时安装依赖，并打开本地字幕服务。以后看课前再双击它，保持窗口打开即可。也可以在此目录打开 PowerShell，手动安装：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. 如果使用手动方式，每次看视频前启动本地服务，并保持终端窗口打开：

   ```powershell
   .\.venv\Scripts\python.exe subtitle_server.py
   ```

3. 在 Chrome 或 Edge 地址栏进入 `chrome://extensions` 或 `edge://extensions`，打开**开发者模式**，点击**加载已解压的扩展程序**，选中本目录的 `extension` 文件夹。安装一次即可。

4. 打开或刷新 B 站视频页。首次处理会暂停视频并提示当前阶段；开头字幕准备好后自动继续播放。播放器底部会显示完整句子。更新扩展代码后，请在扩展管理页点击一次“重新加载”，并重启字幕服务。

## 可选设置

- 不需要字幕时，关闭字幕服务的 CMD 窗口即可。扩展在服务未启动时不会显示提示，也不会暂停视频；使用中关闭服务后，字幕会在几秒内消失。再次启动服务后会自动连接。
- 按住字幕框拖动，可以移动位置；鼠标移到字幕上，拖动右下角的 `↘` 可以同时调整字幕框和文字大小。双击字幕框恢复默认。位置和大小会自动保存，刷新页面、换视频后继续使用，全屏时也会按播放器尺寸调整。

- 如果视频需要登录才能获取，在**启动服务前**运行 `$env:BILI_COOKIE_BROWSER='chrome'`，也可以使用 `edge` 或 `firefox`。程序会尝试读取该浏览器的 B 站登录信息；有的浏览器可能要求先退出才可读取。不要分享 `cache` 目录之外的登录资料。
- 提前处理某个视频：`.\.venv\Scripts\python.exe subtitle_server.py --prepare "https://www.bilibili.com/video/BVxxxxxxxxxx/?p=1"`。
- 默认使用 CPU 上的 `small` 多语言模型。若电脑处理较慢，可在启动前运行 `$env:SUBTITLE_MODEL='base'`；准确率可能下降。设置改变后，同一个视频会重新生成字幕。
- 如课程明确是中文，可在启动前运行 `$env:SUBTITLE_LANGUAGE='zh'`，有时能减少语言识别错误。
- 生成的字幕 JSON 保存在 `cache` 目录；可以删掉对应 JSON 后重新识别。

服务只监听本机 `127.0.0.1:8765`，不需要上传音频到转写服务。下载音频与首次获取模型仍需要联网。
