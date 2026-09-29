import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import subtitle_server as app


def word(start, end, text):
    return SimpleNamespace(start=start, end=end, word=text)


class SubtitleTests(unittest.TestCase):
    def test_course_hints_are_limited_to_relevant_videos(self):
        with patch.object(app, "HOTWORDS", None):
            self.assertIn("int", app.course_hotwords("C++ 教程：关键字"))
            self.assertIn("int", app.course_hotwords("零基础C++教程"))
            self.assertIsNone(app.course_hotwords("English Listening Practice"))
        with patch.object(app, "HOTWORDS", "Fourier, 傅里叶"):
            self.assertEqual(app.course_hotwords("C++"), "Fourier, 傅里叶")

    def test_changed_recognition_settings_do_not_reuse_old_subtitles(self):
        url = "https://www.bilibili.com/video/BV123abc4567/?p=1"
        original = app.cache_path(url)
        for name, value in [("BEAM_SIZE", 1), ("LANGUAGE", "zh"),
                            ("HOTWORDS", "C++ constexpr"), ("MODEL_NAME", "small")]:
            with self.subTest(setting=name), patch.object(app, name, value):
                self.assertNotEqual(original, app.cache_path(url))
        with patch.object(app, "DEVICE", "cpu"):
            self.assertEqual(original, app.cache_path(url))

    def test_mixed_speech_is_transcribed_without_previous_language_prompt(self):
        with patch.object(app, "LANGUAGE", None):
            options = app.transcription_options()
            self.assertTrue(options["multilingual"])
            self.assertFalse(options["condition_on_previous_text"])
            self.assertEqual(options["task"], "transcribe")
            self.assertTrue(options["word_timestamps"])
        with patch.object(app, "LANGUAGE", "en"):
            self.assertFalse(app.transcription_options()["multilingual"])

    def test_auto_device_falls_back_but_forced_cuda_reports_missing_gpu(self):
        fake_ct2 = SimpleNamespace(get_cuda_device_count=lambda: 0)
        with patch.dict(sys.modules, {"ctranslate2": fake_ct2}), \
             patch.object(app, "add_nvidia_library_paths"):
            with patch.object(app, "runtime", None), patch.object(app, "DEVICE", "auto"):
                self.assertEqual(app.get_runtime(), ("cpu", "int8"))
            with patch.object(app, "runtime", None), patch.object(app, "DEVICE", "cuda"):
                with self.assertRaisesRegex(RuntimeError, "SUBTITLE_DEVICE=cpu"):
                    app.get_runtime()

    def test_video_url_and_part(self):
        self.assertEqual(
            app.canonical_video_url("https://www.bilibili.com/video/BV123abc4567?p=2&spm=tracking"),
            "https://www.bilibili.com/video/BV123abc4567/?p=2",
        )
        for value in ["http://www.bilibili.com/video/BV123abc4567",
                      "https://evil.com/video/BV123abc4567",
                      "https://www.bilibili.com/video/BV123abc4567?p=-1"]:
            with self.assertRaises(ValueError):
                app.canonical_video_url(value)

    def test_first_word_has_entire_sentence(self):
        segments = [SimpleNamespace(words=[
            word(1.0, 1.3, "今天"), word(1.3, 1.6, "我们"),
            word(1.6, 1.9, "讲数学。"), word(2.2, 2.5, "先看"),
            word(2.5, 2.8, "公式。"),
        ], text="", start=1, end=3)]
        cues = app.make_cues(segments)
        self.assertEqual([c["text"] for c in cues], ["今天我们讲数学。", "先看公式。"])
        self.assertEqual(cues[0]["start"], 1.0)
        self.assertEqual(cues[1]["start"], 2.2)
        self.assertLessEqual(cues[0]["end"], cues[1]["start"])

    def test_long_pause_splits_sentence(self):
        segment = SimpleNamespace(words=[word(0, .3, "一"), word(.3, .6, "二"),
                                         word(1.5, 1.8, "三")], text="", start=0, end=2)
        self.assertEqual([c["text"] for c in app.make_cues([segment])], ["一二", "三"])

    def test_early_cues_are_published_before_full_transcription(self):
        segments = [
            SimpleNamespace(words=[word(1, 3, "第一句。")], text="", start=0, end=15),
            SimpleNamespace(words=[word(16, 18, "第二句。")], text="", start=15, end=31),
            SimpleNamespace(words=[word(32, 34, "第三句。")], text="", start=31, end=47),
        ]
        progress = []

        def fake_download(command, **_kwargs):
            pattern = command[command.index("-o") + 1]
            Path(pattern.replace("%(ext)s", "m4a")).write_bytes(b"fake audio")
            Path(pattern.replace("%(ext)s", "info.json")).write_text(
                json.dumps({"title": "C++ 关键字"}), encoding="utf-8")
            return SimpleNamespace(returncode=0)

        def fake_transcribe(audio_path, **options):
            self.assertTrue(audio_path.endswith(".m4a"))
            self.assertIn("int", options["hotwords"])
            return iter(segments), None

        fake_model = SimpleNamespace(transcribe=fake_transcribe)
        url = app.canonical_video_url("https://www.bilibili.com/video/BV123abc4567")
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(app, "CACHE", Path(temp)), \
                 patch.object(app, "get_model", return_value=fake_model), \
                 patch.object(app.subprocess, "run", side_effect=fake_download):
                payload = app.prepare(url, progress=lambda cues: progress.append(cues))
                self.assertEqual(progress[0][0]["text"], "第一句。")
                self.assertEqual(len(payload["cues"]), 3)
                self.assertTrue(app.cache_path(url).exists())

    def test_http_rejects_web_page_origin_and_invalid_body(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/api/captions"
        try:
            request = Request(url, data=b'{}', headers={"Origin": "https://example.com"},
                              method="POST")
            with self.assertRaises(HTTPError) as result:
                urlopen(request)
            self.assertEqual(result.exception.code, 403)
            result.exception.close()
            request = Request(url, data=b'[]', method="POST")
            with self.assertRaises(HTTPError) as result:
                urlopen(request)
            self.assertEqual(result.exception.code, 400)
            result.exception.close()
            with patch.object(app, "status_for", return_value={"status": "ready", "cues": []}):
                request = Request(url, data=json.dumps({"url":
                    "https://www.bilibili.com/video/BV123abc4567?p=1"}).encode(),
                    headers={"Origin": "chrome-extension://test"}, method="POST")
                self.assertEqual(json.load(urlopen(request))["status"], "ready")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
