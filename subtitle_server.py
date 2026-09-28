"""Local Bilibili whole-sentence subtitle server.

Run with: python subtitle_server.py
The Chrome/Edge extension in ./extension requests one video page at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
PORT = int(os.environ.get("SUBTITLE_PORT", "8765"))
MODEL_NAME = os.environ.get("SUBTITLE_MODEL", "small")
LANGUAGE = os.environ.get("SUBTITLE_LANGUAGE") or None
VIDEO_RE = re.compile(r"^/video/(BV[0-9A-Za-z]+|av[0-9]+)(?:/)?$", re.I)
HAN = r"\u3400-\u9fff"
executor = ThreadPoolExecutor(max_workers=1)
jobs: dict[str, dict] = {}
lock = threading.Lock()
model = None


def canonical_video_url(raw: str) -> str:
    """Limit requests to a single Bilibili video part and discard tracking params."""
    if not isinstance(raw, str) or len(raw) > 500:
        raise ValueError("视频链接无效")
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or parsed.hostname != "www.bilibili.com":
        raise ValueError("只支持 https://www.bilibili.com/video/ 视频链接")
    match = VIDEO_RE.fullmatch(parsed.path)
    if not match:
        raise ValueError("只支持 B 站普通视频页 /video/BV... 或 /video/av...")
    page_values = parse_qs(parsed.query).get("p", ["1"])
    if len(page_values) != 1 or not page_values[0].isdigit():
        raise ValueError("分 P 参数无效")
    page = int(page_values[0])
    if not 1 <= page <= 1000:
        raise ValueError("分 P 参数超出范围")
    identifier = match.group(1)
    return f"https://www.bilibili.com/video/{identifier}/?p={page}"


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(f"{url}|{MODEL_NAME}|{LANGUAGE}".encode()).hexdigest()[:24]
    return CACHE / f"{digest}.json"


def normalize_text(value: str) -> str:
    value = re.sub(rf"(?<=[{HAN}])\s+(?=[{HAN}])", "", value)
    value = re.sub(rf"\s+(?=[，。！？、；：])", "", value)
    return re.sub(r"\s+", " ", value).strip()


def make_cues(segments) -> list[dict]:
    """Group timed Whisper words into full sentences, starting at the first word."""
    words = []
    for segment in segments:
        if segment.words:
            words.extend(
                (float(w.start), float(w.end), w.word)
                for w in segment.words
                if w.start is not None and w.end is not None and w.word.strip()
            )
        elif segment.text.strip():
            words.append((float(segment.start), float(segment.end), segment.text))

    cues = []
    group = []

    def flush():
        if not group:
            return
        content = normalize_text("".join(item[2] for item in group))
        if content:
            cues.append({"start": round(group[0][0], 2),
                         "end": round(group[-1][1], 2), "text": content})
        group.clear()

    for word in words:
        if group:
            previous = group[-1]
            current_text = normalize_text("".join(item[2] for item in group))
            previous_text = previous[2].rstrip()
            pause = word[0] - previous[1]
            terminal = bool(re.search(r"[。！？!?][”\"']?$", previous_text))
            comma = bool(re.search(r"[，,；;：:]$", previous_text))
            too_long = (len(current_text) + len(word[2].strip()) > 30
                        or word[1] - group[0][0] > 7)
            if (pause >= 0.75 or terminal or (comma and len(current_text) >= 10)
                    or too_long):
                flush()
        group.append(word)
    flush()

    for index, cue in enumerate(cues):
        next_start = cues[index + 1]["start"] if index + 1 < len(cues) else float("inf")
        cue["end"] = round(min(next_start, cue["end"] + 0.55), 2)
    return cues


def set_job(url: str, status: str, **extra):
    with lock:
        jobs[url] = {"status": status, **extra}
    print(f"[{url}] {status}", flush=True)


def get_model():
    global model
    if model is None:
        from faster_whisper import WhisperModel
        model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8",
                             cpu_threads=min(8, os.cpu_count() or 4),
                             download_root=str(CACHE / "models"))
    return model


def prepare(url: str, progress=None) -> dict:
    """Download audio, publish stable early cues, then save the full result."""
    output = cache_path(url)
    if output.exists():
        return json.loads(output.read_text(encoding="utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="subtitle-audio-", dir=CACHE) as temp:
        set_job(url, "downloading")
        command = [sys.executable, "-m", "yt_dlp", "--no-playlist",
                   "--no-progress", "--no-warnings", "-f", "bestaudio/best",
                   "-o", str(Path(temp) / "audio.%(ext)s")]
        browser = os.environ.get("BILI_COOKIE_BROWSER", "").strip().lower()
        if browser:
            if browser not in {"chrome", "edge", "firefox"}:
                raise ValueError("BILI_COOKIE_BROWSER 只能是 chrome、edge 或 firefox")
            command += ["--cookies-from-browser", browser]
        command.append(url)
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=3600)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RuntimeError(detail[-1] if detail else "音频下载失败")
        audio_files = [p for p in Path(temp).iterdir() if p.is_file() and
                       not p.name.endswith((".part", ".ytdl"))]
        if not audio_files:
            raise RuntimeError("音频下载后未找到文件")
        set_job(url, "transcribing")
        segments, _ = get_model().transcribe(str(max(audio_files, key=lambda p: p.stat().st_size)),
                                             language=LANGUAGE, word_timestamps=True,
                                             vad_filter=True, beam_size=1)
        completed_segments = []
        published_through = 0.0
        for segment in segments:
            completed_segments.append(segment)
            if progress and segment.end >= max(30.0, published_through + 15.0):
                # The last cue may continue into the next segment. Hold it back.
                stable = make_cues(completed_segments)[:-1]
                if stable and stable[-1]["end"] > published_through:
                    progress(stable)
                    published_through = stable[-1]["end"]
        cues = make_cues(completed_segments)
    if not cues:
        raise RuntimeError("未识别出人声；请确认视频有可听清的语音")
    payload = {"url": url, "cues": cues, "model": MODEL_NAME}
    pending = output.with_suffix(".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pending.replace(output)
    return payload


def background_prepare(url: str):
    try:
        payload = prepare(url, progress=lambda cues: set_job(url, "partial", cues=cues))
        set_job(url, "ready", cues=payload["cues"])
    except Exception as error:
        set_job(url, "error", message=str(error)[:400])


def status_for(url: str) -> dict:
    output = cache_path(url)
    if output.exists():
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
            return {"status": "ready", "cues": payload["cues"]}
        except (OSError, ValueError, KeyError):
            output.unlink(missing_ok=True)
    with lock:
        existing = jobs.get(url)
        if existing is None:
            jobs[url] = {"status": "queued"}
            executor.submit(background_prepare, url)
            return {"status": "queued"}
        return existing.copy()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/captions":
            return self.reply(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        if origin and not origin.startswith(("chrome-extension://", "edge-extension://")):
            return self.reply(403, {"error": "只接受浏览器扩展请求"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("请求长度无效")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("请求内容必须是 JSON 对象")
            url = canonical_video_url(body.get("url", ""))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            return self.reply(400, {"error": str(error)})
        self.reply(200, status_for(url))

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status": "ok", "model": MODEL_NAME})
        self.reply(404, {"error": "Not found"})

    def reply(self, code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description="B 站完整句字幕服务")
    parser.add_argument("--prepare", metavar="URL", help="提前处理一个 B 站视频")
    args = parser.parse_args()
    if args.prepare:
        url = canonical_video_url(args.prepare)
        payload = prepare(url)
        print(f"已生成 {len(payload['cues'])} 条完整句字幕")
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"字幕服务已启动：http://127.0.0.1:{PORT}/health", flush=True)
    print("保持此窗口打开，再在 Chrome/Edge 中播放 B 站视频。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n字幕服务已停止")
    finally:
        server.server_close()
        executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
