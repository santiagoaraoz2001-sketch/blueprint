const BLUEPRINT_API = "http://localhost:8000";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "CHECK_BLUEPRINT") {
    fetch(`${BLUEPRINT_API}/api/health`, { method: "GET" })
      .then((res) => sendResponse({ running: res.ok }))
      .catch(() => sendResponse({ running: false }));
    return true;
  }

  if (message.type === "IMPORT_DATASET") {
    fetch(`${BLUEPRINT_API}/api/datasets/import/huggingface`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.payload),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => sendResponse({ success: true, data }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
