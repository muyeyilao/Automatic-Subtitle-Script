(() => {
  "use strict";

  const defaults = {x: 0.5, y: 0.86, width: 0.72};
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  globalThis.BiliSubtitleOverlay = class {
    constructor(getVideo) {
      this.getVideo = getVideo;
      this.layout = {...defaults};
      this.host = null;
      this.gesture = null;
      this.touched = false;
      this.muted = false;
      try {
        chrome.storage.local.get("subtitleLayout", (stored) => {
          if (chrome.runtime.lastError || this.touched) return;
          const saved = stored?.subtitleLayout;
          if (!saved) return;
          for (const [key, value] of Object.entries(saved)) {
            if (Object.hasOwn(defaults, key) && Number.isFinite(value)) {
              this.layout[key] = clamp(value, key === "width" ? 0.28 : 0,
                                      key === "width" ? 0.96 : 1);
            }
          }
          this.position();
        });
      } catch { /* An extension reload invalidates the old page's context. */ }
    }

    create() {
      if (this.host?.isConnected) return;
      this.host = document.createElement("div");
      this.host.setAttribute("data-whole-sentence-subtitles", "");
      this.host.style.cssText = "all:initial;position:fixed;z-index:2147483647;display:none;" +
        "box-sizing:border-box;pointer-events:auto;";
      const shadow = this.host.attachShadow({mode: "open"});
      const style = document.createElement("style");
      style.textContent = `
        .frame { position:relative; box-sizing:border-box; width:100%; padding:6px 22px 6px 12px;
          border-radius:5px; background:rgba(0,0,0,.66); color:white; text-align:center;
          font-family:Arial,'Microsoft YaHei',sans-serif; font-weight:600; line-height:1.42;
          text-shadow:0 1px 3px black; overflow-wrap:anywhere; cursor:move;
          touch-action:none; user-select:none; }
        .frame:focus-visible { outline:2px solid #70cfff; }
        .text { pointer-events:none; }
        .resize { all:unset; position:absolute; right:0; bottom:0; width:22px; height:22px;
          box-sizing:border-box; color:white; font:20px/22px Arial,sans-serif;
          text-align:center; cursor:nwse-resize; opacity:0; touch-action:none; }
        .frame:hover .resize, .frame:focus-within .resize, .dragging .resize { opacity:1; }
      `;
      this.frame = document.createElement("div");
      this.frame.className = "frame";
      this.frame.tabIndex = 0;
      this.frame.title = "拖动字幕移动位置；拖动右下角缩放；双击恢复默认";
      this.text = document.createElement("span");
      this.text.className = "text";
      this.handle = document.createElement("button");
      this.handle.className = "resize";
      this.handle.type = "button";
      this.handle.textContent = "↘";
      this.handle.title = "拖动调整字幕和文字大小";
      this.handle.setAttribute("aria-label", this.handle.title);
      this.frame.append(this.text, this.handle);
      shadow.append(style, this.frame);
      this.frame.addEventListener("pointerdown", (event) => this.begin(event));
      this.frame.addEventListener("pointermove", (event) => this.move(event));
      for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
        this.frame.addEventListener(name, (event) => {
          if (this.gesture?.id === event.pointerId) this.finish();
        });
      }
      this.frame.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
      });
      this.frame.addEventListener("dblclick", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this.finish(false);
        this.layout = {...defaults};
        this.touched = true;
        this.save();
        this.position();
      });
      document.body.appendChild(this.host);
    }

    bounds() {
      const rect = this.getVideo()?.getBoundingClientRect();
      return rect && rect.width > 0 && rect.height > 0 ? rect : null;
    }

    show(text, muted = false) {
      // Keep the current sentence under the pointer throughout a drag.
      if (this.gesture) {
        this.position();
        return;
      }
      if (!text) {
        this.hide();
        return;
      }
      this.create();
      this.muted = muted;
      this.text.textContent = text;
      this.host.style.display = "block";
      this.position();
    }

    hide() {
      this.finish(false);
      if (this.host) this.host.style.display = "none";
    }

    position() {
      if (!this.host?.isConnected || this.host.style.display === "none") return;
      const bounds = this.bounds();
      if (!bounds) return;
      const fullscreen = document.fullscreenElement;
      const parent = fullscreen || document.body;
      if (this.host.parentNode !== parent) {
        this.finish(false);
        parent.appendChild(this.host);
      }
      this.host.style.visibility = bounds.bottom <= 0 || bounds.top >= innerHeight
        || bounds.right <= 0 || bounds.left >= innerWidth ? "hidden" : "visible";
      const margin = Math.min(8, bounds.width * 0.02, bounds.height * 0.02);
      const width = Math.min(bounds.width - 2 * margin, bounds.width * this.layout.width);
      this.host.style.width = `${width}px`;
      const font = clamp(bounds.width * 0.032, 18, 36) * this.layout.width / defaults.width;
      this.frame.style.fontSize = `${Math.max(12, font * (this.muted ? 0.65 : 1))}px`;
      const height = this.host.getBoundingClientRect().height;
      const left = bounds.left + clamp(this.layout.x * bounds.width - width / 2,
        margin, Math.max(margin, bounds.width - margin - width));
      const top = bounds.top + clamp(this.layout.y * bounds.height - height / 2,
        margin, Math.max(margin, bounds.height - margin - height));
      const origin = fullscreen?.getBoundingClientRect();
      this.host.style.position = fullscreen ? "absolute" : "fixed";
      this.host.style.left = `${left - (origin?.left || 0)}px`;
      this.host.style.top = `${top - (origin?.top || 0)}px`;
    }

    begin(event) {
      if (event.button !== 0 || this.gesture) return;
      const bounds = this.bounds();
      if (!bounds) return;
      event.preventDefault();
      event.stopPropagation();
      this.touched = true;
      this.gesture = {
        id: event.pointerId, mode: event.target === this.handle ? "resize" : "move",
        x: event.clientX, y: event.clientY, bounds,
        rect: this.host.getBoundingClientRect(), width: this.layout.width,
      };
      this.frame.classList.add("dragging");
      try { this.frame.setPointerCapture(event.pointerId); } catch { /* Pointer ended. */ }
    }

    move(event) {
      const gesture = this.gesture;
      if (!gesture || gesture.id !== event.pointerId) return;
      event.preventDefault();
      event.stopPropagation();
      const {bounds, rect} = gesture;
      if (gesture.mode === "move") {
        this.layout.x = clamp((rect.left + rect.width / 2 + event.clientX - gesture.x
          - bounds.left) / bounds.width, 0, 1);
        this.layout.y = clamp((rect.top + rect.height / 2 + event.clientY - gesture.y
          - bounds.top) / bounds.height, 0, 1);
      } else {
        const ratio = 1 + (event.clientX - gesture.x + event.clientY - gesture.y)
          / (rect.width + rect.height);
        this.layout.width = clamp(gesture.width * ratio, 0.28, 0.96);
        this.position();
        const resized = this.host.getBoundingClientRect();
        this.layout.x = clamp((rect.left + resized.width / 2 - bounds.left) / bounds.width, 0, 1);
        this.layout.y = clamp((rect.top + resized.height / 2 - bounds.top) / bounds.height, 0, 1);
      }
      this.position();
    }

    finish(save = true) {
      if (!this.gesture) return;
      const id = this.gesture.id;
      this.gesture = null;
      this.frame.classList.remove("dragging");
      if (this.frame.hasPointerCapture(id)) this.frame.releasePointerCapture(id);
      if (save) {
        const bounds = this.bounds();
        const rect = this.host.getBoundingClientRect();
        if (bounds) {
          this.layout.x = clamp((rect.left + rect.width / 2 - bounds.left) / bounds.width, 0, 1);
          this.layout.y = clamp((rect.top + rect.height / 2 - bounds.top) / bounds.height, 0, 1);
        }
        this.save();
      }
    }

    save() {
      try {
        chrome.storage.local.set({subtitleLayout: {...this.layout}}, () => {
          void chrome.runtime.lastError;
        });
      } catch { /* Leave the current adjustment usable if storage is unavailable. */ }
    }
  };
})();
