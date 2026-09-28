# 扩展行为验证

- 在项目目录运行 `node --test tests/test_background.cjs`，检查服务关闭与请求错误的处理。
- 在项目目录运行 `python -m http.server 18765 --bind 127.0.0.1`，打开 `http://127.0.0.1:18765/tests/extension_harness.html`，页面会验证服务离线、自动暂停与恢复、拖动、缩放、保存布局及全屏容器切换。测试使用模拟服务和视频状态，不下载音频或模型。测试后关闭这个 HTTP 服务即可。
- 页面显示全部 PASS 后，也可以直接拖动示例字幕和右下角手柄，检查鼠标操作。
