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

   有 NVIDIA 显卡时，先在项目目录安装一次显卡运行库（需要兼容 CUDA 12 的驱动）：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements-gpu.txt
   ```

   运行库只装在本项目 `.venv` 中。启动窗口会显示实际使用的 `cuda/int8_float16` 或 `cpu/int8`；缺少显卡或运行库时会提示并退回 CPU，处理较慢。

3. 在 Chrome 或 Edge 地址栏进入 `chrome://extensions` 或 `edge://extensions`，打开**开发者模式**，点击**加载已解压的扩展程序**，选中本目录的 `extension` 文件夹。安装一次即可。

4. 打开或刷新 B 站视频页。首次处理会暂停视频并提示当前阶段；开头字幕准备好后自动继续播放。播放器底部会显示完整句子。更新扩展代码后，请在扩展管理页点击一次“重新加载”，并重启字幕服务。

## 可选设置

- 不需要字幕时，关闭字幕服务的 CMD 窗口即可。扩展在服务未启动时不会显示提示，也不会暂停视频；使用中关闭服务后，字幕会在几秒内消失。再次启动服务后会自动连接。
- 按住字幕框拖动，可以移动位置；鼠标移到字幕上，拖动右下角的 `↘` 可以同时调整字幕框和文字大小。双击字幕框恢复默认。位置和大小会自动保存，刷新页面、换视频后继续使用，全屏时也会按播放器尺寸调整。

- 如果视频需要登录才能获取，在**启动服务前**运行 `$env:BILI_COOKIE_BROWSER='chrome'`，也可以使用 `edge` 或 `firefox`。程序会尝试读取该浏览器的 B 站登录信息；有的浏览器可能要求先退出才可读取。不要分享 `cache` 目录之外的登录资料。
- 提前处理某个视频：`.\.venv\Scripts\python.exe subtitle_server.py --prepare "https://www.bilibili.com/video/BVxxxxxxxxxx/?p=1"`。
- 默认模型为 `large-v3-turbo`，优先使用 NVIDIA 显卡和 `int8_float16` 精度，CPU 使用 `int8`。模型约 1.6 GB，第一次下载后保存在 `cache/models`；显卡运行库另占 `.venv` 空间。旧 `small` 模型不会自动删除。
- 默认逐段自动识别语言，适合中英混讲，按原文转写；关闭前一段字幕的连续提示以减少错误传播和重复。只看单一语言时可设置 `$env:SUBTITLE_LANGUAGE='zh'` 或 `'en'`；恢复自动识别用 `'auto'`。中英切换的效果仍取决于音频，不能保证没有漏词或误译。
- 默认搜索宽度为 `5`。若更重视速度，可设置 `$env:SUBTITLE_BEAM_SIZE='3'` 或 `'1'`；准确率变化需按课程实测。低置信片段最多使用三档温度尝试，避免反复重试拖慢识别。
- 标题包含 `C++` 的视频会自动使用少量编程术语提示，帮助区分 `int`、常量、变量等词；其他课程默认不加术语。可设置 `$env:SUBTITLE_HOTWORDS='C++, constexpr, std::cout, 常量, 变量'` 覆盖自动提示；只填当前课程相关词，不宜加入大量无关词。提示只辅助识别，不会把已识别的字幕机械替换成指定词。
- 没有显卡且速度过慢时，可设置 `$env:SUBTITLE_MODEL='small'`；准确率可能下降。可用 `$env:SUBTITLE_DEVICE='cpu'` 强制 CPU，或用 `'cuda'` 要求显卡（不可用时明确报错）。
- 上述 PowerShell 环境变量只对该终端及其子进程有效：设置后在同一个窗口执行 `.\.venv\Scripts\python.exe subtitle_server.py`。双击启动器时默认使用本节的默认配置。
- 生成的字幕 JSON 保存在 `cache`；模型、语言、搜索宽度或术语提示改变后会重新识别，升级也不会继续读取旧版字幕。关闭字幕服务后，可以删除 `cache` 中除 `models` 外的缓存；删掉 `models` 会导致模型重新下载。

服务只监听本机 `127.0.0.1:8765`，不需要上传音频到转写服务。下载音频与首次获取模型仍需要联网。
