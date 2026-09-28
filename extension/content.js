(() => {
  "use strict";

  let pageUrl = "";
  let video = null;
  let cues = [];
  let state = "offline";
  let serviceAvailable = false;
  let pageGeneration = 0;
  let errorText = "";
  let busy = false;
  let autoPausedVideo = null;
  let autoPausedAt = 0;
  const overlay = new BiliSubtitleOverlay(() => video);

  const labels = {
    queued: "字幕排队中，视频已暂停",
    downloading: "正在下载音频并准备字幕，视频已暂停…",
    transcribing: "正在识别开头的语音，稍后开始播放…",
    partial: "正在生成后续字幕…",
  };

  function canonicalPage() {
    const match = location.pathname.match(/^\/video\/(BV[0-9A-Za-z]+|av[0-9]+)\/?$/i);
    if (!match) return "";
    const p = Number(new URLSearchParams(location.search).get("p") || "1");
    if (!Number.isInteger(p) || p < 1 || p > 1000) return "";
    return `https://www.bilibili.com/video/${match[1]}/?p=${p}`;
  }

  function findVideo() {
    return [...document.querySelectorAll("video")]
      .filter((item) => item.isConnected && item.getBoundingClientRect().width > 100)
      .sort((a, b) => {
        const ra = a.getBoundingClientRect();
        const rb = b.getBoundingClientRect();
        return rb.width * rb.height - ra.width * ra.height;
      })[0] || null;
  }

  function waitingForCues() {
    if (!serviceAvailable || state === "ready" || state === "error") return false;
    if (state !== "partial") return true;
    const last = cues[cues.length - 1];
    return !last || video.currentTime >= last.end - 0.08;
  }

  function pauseUntilReady() {
    if (video && waitingForCues() && !video.paused) {
      autoPausedVideo = video;
      autoPausedAt = video.currentTime;
      video.pause();
    }
  }

  function resumeAutoPaused(rewind = false) {
    const target = autoPausedVideo;
    autoPausedVideo = null;
    if (target !== video || !target?.paused) return;
    if (rewind && Math.abs(target.currentTime - autoPausedAt) < 0.2)
      target.currentTime = Math.max(0, autoPausedAt - 0.4);
    target.play().catch(() => {});
  }

  function goOffline() {
    serviceAvailable = false;
    state = "offline";
    cues = [];
    errorText = "";
    overlay.hide();
    resumeAutoPaused();
  }

  function cueAt(time) {
    let lo = 0;
    let hi = cues.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (cues[mid].start <= time) {
        found = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    const cue = cues[found];
    return cue && time <= cue.end ? cue.text : "";
  }

  function render() {
    if (!video || !serviceAvailable) {
      overlay.hide();
      return;
    }
    if (state === "ready" || state === "partial") {
      const text = cueAt(video.currentTime);
      overlay.show(text || (state === "partial" && waitingForCues() ? labels.partial : ""), !text);
    }
    else if (state === "error") overlay.show(`字幕失败：${errorText}`, true);
    else overlay.show(labels[state] || "正在准备字幕…", true);
  }

  function fetchStatus() {
    if (!pageUrl || busy) return;
    busy = true;
    const generation = pageGeneration;
    // Completed captions still check service health, so closing CMD disables them.
    const type = serviceAvailable && state === "ready" ? "health" : "captions";
    const receive = (reply) => {
      const transportError = chrome.runtime.lastError;
      busy = false;
      if (generation !== pageGeneration) return;
      if (transportError || !reply || (!reply.ok && reply.unavailable !== false)) {
        goOffline();
        return;
      }
      serviceAvailable = true;
      if (!reply.ok) {
        state = "error";
        errorText = reply.error || "服务请求失败";
        resumeAutoPaused();
        render();
        return;
      }
      if (type === "health") return;
      const result = reply.body;
      state = result.status;
      if (state === "ready" || state === "partial") {
        cues = result.cues || [];
        if (video && !waitingForCues()) resumeAutoPaused(true);
      } else if (state === "error") {
        errorText = result.message || "未知错误";
        resumeAutoPaused();
      } else pauseUntilReady();
      render();
    };
    try {
      chrome.runtime.sendMessage({type, url: pageUrl}, receive);
    } catch {
      busy = false;
      goOffline();
    }
  }

  function checkPage() {
    const currentUrl = canonicalPage();
    const currentVideo = findVideo();
    video = currentVideo;
    if (currentUrl !== pageUrl) {
      pageUrl = currentUrl;
      pageGeneration += 1;
      cues = [];
      state = "offline";
      serviceAvailable = false;
      errorText = "";
      autoPausedVideo = null;
      autoPausedAt = 0;
      overlay.hide();
      if (pageUrl) fetchStatus();
    }
    if (pageUrl && video) pauseUntilReady();
    if (!pageUrl || !video) overlay.hide();
    else render();
  }

  setInterval(checkPage, 250);
  setInterval(fetchStatus, 2500);
  checkPage();
})();
