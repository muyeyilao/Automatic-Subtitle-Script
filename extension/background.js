chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const health = message?.type === "health";
  if (!health && (message?.type !== "captions" || typeof message.url !== "string")) return;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2000);
  fetch(`http://127.0.0.1:8765/${health ? "health" : "api/captions"}`, health ? {
    signal: controller.signal,
    cache: "no-store",
  } : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({url: message.url}),
    signal: controller.signal,
  })
    .then(async (response) => {
      const body = await response.json();
      if (!response.ok) sendResponse({ok: false, unavailable: false,
        error: body.error || `HTTP ${response.status}`});
      else sendResponse({ok: true, body});
    })
    .catch((error) => sendResponse({ok: false, unavailable: true,
      error: String(error.message || error)}))
    .finally(() => clearTimeout(timeout));
  return true;
});
