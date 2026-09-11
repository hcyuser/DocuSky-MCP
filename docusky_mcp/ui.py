"""MCP Apps (interactive UI) support for the DocuSky MCP server.

Wires `search_documents`, `post_classification`, and `tag_analysis` to a
`ui://` resource so hosts that support the MCP Apps extension
(https://modelcontextprotocol.io/extensions/apps/overview) render DocuSky's
own web page inline, in a sandboxed iframe, instead of only text.

How it works
------------
The tool functions are unchanged: they still return the same JSON text they
always did (so plain, non-Apps clients keep working exactly as before), with
one extra field added to the payload -- ``webUrl`` -- pointing at the
matching page on docusky.org.tw. Even a client with no MCP Apps support still
gets this field and can offer it to the user as a plain link.

This module's HTML resource is a small, dependency-free implementation of
the MCP Apps postMessage protocol (wire format:
https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx).
It performs the `ui/initialize` handshake, waits for the
`ui/notifications/tool-result` notification, pulls `webUrl` out of the JSON
text content, and points an `<iframe>` at it. It intentionally does not
depend on the `@modelcontextprotocol/ext-apps` npm package, so this project
stays pure Python with no JS build step.

Why `target="OPEN"` only
------------------------
DocuSky authenticates with a session cookie held by *this server's* own
httpx client. The viewer's browser (inside the sandboxed iframe) does not
share that cookie, so an embedded "USER" (private-database) page would just
show a logged-out DocuSky -- confusing, not useful. `build_viewer_url`
returns None for anything but "OPEN", and the affected tools fall back to
plain text only, exactly as before this feature existed.

Verified live against https://docusky.org.tw on 2026-09-11
------------------------------------------------------------
* `webApi/webpage-open-3in1.php` (with `spType=postClassification` /
  `spType=tagAnalysis` / no `spType` at all) renders real data for a public
  database, and its response carries neither `X-Frame-Options` nor a
  framing `Content-Security-Policy`, so it can be embedded in an iframe.
* The narrower `docuTools/*Lite` widgets (CatDistributionLite, TagStatsTool,
  SimTextsLite, ...) were NOT used here even though they also lack framing
  restrictions: they appear to be driven by a JS API from their own parent
  page rather than plain URL query parameters -- one tested standalone with
  guessed `target`/`db`/`corpus`/`query` params simply rendered blank. If
  DocuSky documents that API later, swapping the URL builder below is all
  that's needed; the postMessage/rendering side does not change.
"""

from __future__ import annotations

from urllib.parse import urlencode

DOCUSKY_SITE_BASE = "https://docusky.org.tw/DocuSky"
VIEWER_RESOURCE_URI = "ui://docusky/viewer.html"


def build_viewer_url(
    db: str,
    corpus: str,
    query: str,
    target: str,
    sp_type: str | None = None,
) -> str | None:
    """Build a docusky.org.tw URL for embedding, or None when it would not work.

    Only "OPEN" (public) databases are embeddable -- see the module docstring.
    """
    if (target or "OPEN").upper() != "OPEN":
        return None
    params = {
        "db": db,
        "corpus": corpus,
        "queryBase": query,
        "snippets": "null",
    }
    if sp_type:
        params["spType"] = sp_type
    return f"{DOCUSKY_SITE_BASE}/webApi/webpage-open-3in1.php?{urlencode(params)}"


VIEWER_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>DocuSky 網頁檢視</title>
<style>
  :root { color-scheme: light dark; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; flex-direction: column;
    font: 13px/1.5 -apple-system, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
    background: #fff; color: #1a1a1a;
  }
  body.theme-dark { background: #1e1e1e; color: #e6e6e6; }
  #frame { flex: 1 1 auto; border: 0; width: 100%; min-height: 480px; background: #fff; }
  .msg { margin: auto; padding: 24px; text-align: center; max-width: 32em; }
  .msg code { display: block; margin-top: 8px; white-space: pre-wrap; word-break: break-all; opacity: 0.75; font-size: 12px; }
  a { color: inherit; }
</style>
</head>
<body>
<div id="root" class="msg">正在連接 DocuSky…</div>
<script>
(function () {
  "use strict";
  var settled = false;

  function showMessage(text, detail) {
    document.body.innerHTML = '<div id="root" class="msg"></div>';
    var root = document.getElementById("root");
    root.appendChild(document.createTextNode(text));
    if (detail) {
      var code = document.createElement("code");
      code.textContent = detail;
      root.appendChild(code);
    }
  }

  function showIframe(url) {
    settled = true;
    document.body.innerHTML = "";
    var frame = document.createElement("iframe");
    frame.id = "frame";
    frame.src = url;
    frame.title = "DocuSky";
    frame.loading = "lazy";
    document.body.appendChild(frame);
  }

  function applyTheme(hostContext) {
    if (hostContext && hostContext.theme === "dark") {
      document.body.classList.add("theme-dark");
    }
  }

  function handleToolResult(params) {
    settled = true;
    var content = (params && params.content) || [];
    var textBlock = null;
    for (var i = 0; i < content.length; i++) {
      if (content[i] && content[i].type === "text") { textBlock = content[i]; break; }
    }
    var data = null;
    if (textBlock) {
      try { data = JSON.parse(textBlock.text); } catch (e) { /* not JSON, ignore */ }
    }
    if (data && data.webUrl) {
      showIframe(data.webUrl);
    } else if (data && data.error) {
      showMessage("DocuSky 回傳了錯誤：", data.error);
    } else {
      showMessage(
        "這次查詢沒有可內嵌顯示的 DocuSky 網頁（多半是私人資料庫查詢，需要在瀏覽器另外登入 DocuSky）。",
        textBlock ? String(textBlock.text).slice(0, 500) : null
      );
    }
  }

  function post(msg) {
    window.parent.postMessage(msg, "*");
  }

  window.addEventListener("message", function (event) {
    var msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;
    if (msg.id === 1 && msg.result) {
      applyTheme(msg.result.hostContext);
      post({ jsonrpc: "2.0", method: "ui/notifications/initialized" });
    } else if (msg.method === "ui/notifications/tool-result") {
      handleToolResult(msg.params);
    }
  });

  post({
    jsonrpc: "2.0",
    id: 1,
    method: "ui/initialize",
    params: { appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] } }
  });

  setTimeout(function () {
    if (!settled) {
      showMessage("尚未收到查詢結果。這個 MCP 用戶端可能不支援 MCP Apps 內嵌顯示。");
    }
  }, 8000);
})();
</script>
</body>
</html>
"""
