"""MCP Apps (interactive UI) support for the DocuSky MCP server.

Wires `search_documents`, `post_classification`, `tag_analysis` and
`word_cloud` to a `ui://` resource so hosts that support the MCP Apps
extension (https://modelcontextprotocol.io/extensions/apps/overview) render
DocuSky's own web page inline, in a sandboxed iframe, instead of only text.

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
text content, and points an `<iframe>` at it, under a thin toolbar of its own
(paging, fullscreen, open-in-browser, reload). It intentionally does not
depend on the `@modelcontextprotocol/ext-apps` npm package, so this project
stays pure Python with no JS build step.

Three things the published schema and a live DocuSky make non-negotiable, all
learned the hard way (see "Verified live", below):

* `ui/initialize` params REQUIRE `appInfo`, `appCapabilities` *and*
  `protocolVersion`. Sending only `appCapabilities` (as this file did before
  2026-09-12) is invalid params: a host that validates the request rejects the
  handshake, never pushes the tool result, and the viewer shows nothing.
* DocuSky's own paginator navigates the whole frame
  (`window.location.href = ...` inside its `requestNewPage`), which comes back
  blank inside a sandboxed iframe. Loading `&page=N` as the frame's `src`
  works, so the toolbar drives paging itself and the note under it warns the
  user off DocuSky's own page buttons.
* The viewer asks the host for a 720px-tall inline frame
  (`ui/notifications/size-changed`) and offers a fullscreen toggle
  (`ui/request-display-mode`); a retrieval page in a default-height strip is
  not usable.

Why `target="OPEN"` only
------------------------
DocuSky authenticates with a session cookie held by *this server's* own
httpx client. The viewer's browser (inside the sandboxed iframe) does not
share that cookie, so an embedded "USER" (private-database) page would just
show a logged-out DocuSky -- confusing, not useful. `build_viewer_url`
returns None for anything but "OPEN", and the affected tools fall back to
plain text only, exactly as before this feature existed. `word_cloud` (see
`build_wordcloud_url` at the bottom of this file) is unaffected: it embeds a
stateless tool page whose whole input travels in the URL, so it needs no
DocuSky session at all.

Verified live against https://docusky.org.tw on 2026-09-11 / 2026-09-12
-----------------------------------------------------------------------
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
  WordCloudLite turned out to be the exception (added 2026-09-12): its source
  does document two query parameters, so `build_wordcloud_url` drives it
  directly -- see the comment above that function.

Sandbox behaviour, measured 2026-09-12 by replaying the reference host
(`examples/basic-host` in ext-apps: an outer proxy iframe on its own origin
plus an inner `sandbox`ed iframe) against the real docusky.org.tw:

* `allow-scripts allow-same-origin allow-forms` (what the reference host sets,
  and what any host that injects the HTML with `document.write` must set):
  every page of results renders, and the toolbar's `&page=N` paging works.
  DocuSky's own paginator still does not -- see above.
* `allow-scripts` without `allow-same-origin` (some hosts, via `srcdoc`):
  page 1 renders, later pages come back blank no matter how they are
  requested. The viewer detects this (storage access throws), hides its pager,
  and points the user at "open in browser" instead of pretending to page.
"""

from __future__ import annotations

import json
from typing import Any
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
  :root { color-scheme: light dark; --fg: #1a1a1a; --bg: #fff; --bar: #f3f4f6; --line: #d8dade; }
  body.theme-dark { --fg: #e6e6e6; --bg: #1e1e1e; --bar: #2a2b2e; --line: #3a3b3f; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; flex-direction: column; background: var(--bg); color: var(--fg);
    font: 13px/1.5 -apple-system, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
  }
  #bar {
    display: flex; align-items: center; gap: 6px; flex: 0 0 auto;
    padding: 5px 8px; background: var(--bar); border-bottom: 1px solid var(--line);
    font-size: 12px; flex-wrap: wrap;
  }
  #label { opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 45%; }
  .spacer { flex: 1 1 auto; }
  button {
    font: inherit; color: inherit; background: transparent;
    border: 1px solid var(--line); border-radius: 5px; padding: 2px 8px; cursor: pointer;
  }
  button:hover:not(:disabled) { background: rgba(127, 127, 127, 0.16); }
  button:disabled { opacity: 0.4; cursor: default; }
  #jump { width: 4.5em; font: inherit; color: inherit; background: var(--bg);
          border: 1px solid var(--line); border-radius: 5px; padding: 2px 4px; }
  #pager { display: flex; align-items: center; gap: 4px; }
  #note { flex: 0 0 auto; padding: 4px 10px; font-size: 11px; opacity: 0.75;
          background: var(--bar); border-bottom: 1px solid var(--line); }
  #frame { flex: 1 1 auto; border: 0; width: 100%; background: #fff; transition: opacity 0.15s; }
  #frame.loading { opacity: 0.35; }
  #spin { opacity: 0.7; }
  .msg { margin: auto; padding: 24px; text-align: center; max-width: 32em; }
  .msg code { display: block; margin-top: 8px; white-space: pre-wrap; word-break: break-all;
              opacity: 0.75; font-size: 12px; }
</style>
</head>
<body>
<div id="root" class="msg">正在連接 DocuSky…</div>
<script>
(function () {
  "use strict";

  // Wire format: https://github.com/modelcontextprotocol/ext-apps
  //              /blob/main/specification/2026-01-26/apps.mdx
  var PROTOCOL_VERSION = "2026-01-26";
  var APP_INFO = { name: "docusky-viewer", version: "0.3.1", title: "DocuSky 網頁檢視" };
  var INLINE_HEIGHT = 720;      // px asked of the host for the inline iframe
  var DOCUSKY_PAGE_SIZE = 20;   // what webpage-open-3in1.php itself pages by

  var nextId = 2;                 // id 1 is the ui/initialize request
  var waiting = {};               // JSON-RPC id -> callback
  var host = { capabilities: {}, context: {}, displayMode: "inline" };
  var view = { base: null, page: 1, totalPages: null, pageable: false };
  var settled = false;

  // Hosts sandbox this document, and sandbox flags are inherited by the nested
  // docusky.org.tw frame. Without `allow-same-origin` that frame lives in an
  // opaque origin, and DocuSky's results page then renders page 1 only -- every
  // later page comes back blank (verified against docusky.org.tw, 2026-09-12).
  // Storage throwing is the same signal, so probe it and, in that case, offer
  // "open in browser" instead of a pager that would only produce blanks.
  var strictSandbox = (function () {
    try { window.localStorage.getItem("docusky-probe"); return false; }
    catch (e) { return true; }
  })();

  function post(msg) { window.parent.postMessage(msg, "*"); }

  function request(method, params, onResult) {
    var id = nextId++;
    if (onResult) waiting[id] = onResult;
    post({ jsonrpc: "2.0", id: id, method: method, params: params });
  }

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

  function applyTheme(context) {
    document.body.classList.toggle("theme-dark", !!context && context.theme === "dark");
  }

  // --- URL helpers ------------------------------------------------------
  // DocuSky's own paginator navigates the frame to the same page with
  // `&page=N` appended (verified live), so page N is just a URL away.

  function stripPage(url) {
    return url
      .replace(/[?&]page=\d+/g, function (m) { return m.charAt(0) === "?" ? "?" : ""; })
      .replace(/\?&/, "?")
      .replace(/[?&]$/, "");
  }

  function pageUrl(url, page) {
    if (page <= 1) return url;
    return url + (url.indexOf("?") === -1 ? "?" : "&") + "page=" + page;
  }

  // --- rendering --------------------------------------------------------
  //
  // The toolbar is rebuilt on every state change, but the <iframe> element is
  // created once and only ever has its `src` reassigned: rebuilding it would
  // re-fetch a ~500 KB DocuSky page just to relabel a button.

  var els = null;

  function mount() {
    document.body.innerHTML = "";

    var bar = document.createElement("div");
    bar.id = "bar";

    var note = document.createElement("div");
    note.id = "note";
    note.textContent = strictSandbox
      ? "這個用戶端把內嵌網頁鎖在最嚴格的沙箱裡，DocuSky 只有第一頁能正常顯示：要翻頁、篩選或點開單篇，"
        + "請按「瀏覽器開啟」。"
      : "提醒：DocuSky 頁面自己那排翻頁按鈕在內嵌視窗中會翻出空白頁（它靠的整頁跳轉在沙箱 iframe 裡不"
        + "成立）；請改用上方工具列翻頁，或按「瀏覽器開啟」用完整功能。";

    var frame = document.createElement("iframe");
    frame.id = "frame";
    frame.title = "DocuSky";
    frame.className = "loading";
    frame.addEventListener("load", function () {
      frame.classList.remove("loading");
      if (els) els.spin.hidden = true;
    });

    document.body.appendChild(bar);
    document.body.appendChild(note);
    document.body.appendChild(frame);
    els = { bar: bar, note: note, frame: frame, spin: null };
    renderBar();
    note.hidden = !view.pageable;
    load(view.page, true);
  }

  function renderBar() {
    if (!els) return;
    var bar = els.bar;
    bar.innerHTML = "";

    var label = document.createElement("span");
    label.id = "label";
    label.textContent = view.label || "DocuSky";
    bar.appendChild(label);

    var spin = document.createElement("span");
    spin.id = "spin";
    spin.textContent = "載入中…";
    spin.hidden = !els.frame.classList.contains("loading");
    bar.appendChild(spin);
    els.spin = spin;

    if (view.pageable && !strictSandbox) bar.appendChild(buildPager());

    var spacer = document.createElement("span");
    spacer.className = "spacer";
    bar.appendChild(spacer);

    if ((host.context.availableDisplayModes || []).indexOf("fullscreen") !== -1) {
      bar.appendChild(button(host.displayMode === "fullscreen" ? "⤡ 結束全螢幕" : "⤢ 全螢幕", function () {
        var mode = host.displayMode === "fullscreen" ? "inline" : "fullscreen";
        request("ui/request-display-mode", { mode: mode }, function (result) {
          if (result && result.mode) { host.displayMode = result.mode; renderBar(); }
        });
      }));
    }
    if (host.capabilities.openLinks) {
      bar.appendChild(button("↗ 瀏覽器開啟", function () {
        request("ui/open-link", { url: pageUrl(view.base, view.page) });
      }));
    }
    bar.appendChild(button("⟳", function () { load(view.page, true); }, "重新載入"));
  }

  function button(text, onClick, title) {
    var el = document.createElement("button");
    el.textContent = text;
    if (title) el.title = title;
    el.addEventListener("click", onClick);
    return el;
  }

  function buildPager() {
    var wrap = document.createElement("span");
    wrap.id = "pager";

    var prev = button("‹ 上一頁", function () { load(view.page - 1); });
    prev.disabled = view.page <= 1;
    wrap.appendChild(prev);

    var info = document.createElement("span");
    info.textContent = view.totalPages
      ? "第 " + view.page + " / " + view.totalPages + " 頁"
      : "第 " + view.page + " 頁";
    wrap.appendChild(info);

    var next = button("下一頁 ›", function () { load(view.page + 1); });
    next.disabled = !!view.totalPages && view.page >= view.totalPages;
    wrap.appendChild(next);

    var jump = document.createElement("input");
    jump.id = "jump";
    jump.type = "number";
    jump.min = "1";
    if (view.totalPages) jump.max = String(view.totalPages);
    jump.placeholder = "頁";
    jump.addEventListener("keydown", function (e) {
      if (e.key === "Enter") load(parseInt(jump.value, 10));
    });
    wrap.appendChild(jump);
    wrap.appendChild(button("跳頁", function () { load(parseInt(jump.value, 10)); }));
    return wrap;
  }

  function load(page, force) {
    if (!page || page < 1) page = 1;
    if (view.totalPages && page > view.totalPages) page = view.totalPages;
    if (!force && page === view.page && els) return;
    view.page = page;
    els.frame.classList.add("loading");
    els.frame.src = pageUrl(view.base, view.page);
    renderBar();
  }

  // --- tool result ------------------------------------------------------

  function handleToolResult(params) {
    settled = true;
    var content = (params && params.content) || [];
    var data = (params && params.structuredContent) || null;
    var textBlock = null;
    for (var i = 0; i < content.length; i++) {
      if (content[i] && content[i].type === "text") { textBlock = content[i]; break; }
    }
    if (!data && textBlock) {
      try { data = JSON.parse(textBlock.text); } catch (e) { /* not JSON, ignore */ }
    }
    // The SDK may hand structured output back wrapped in a single "result" key.
    if (data && typeof data.result === "string" && !data.webUrl) {
      try { data = JSON.parse(data.result); } catch (e) { /* keep what we have */ }
    }

    if (data && data.webUrl) {
      view.base = stripPage(data.webUrl);
      view.page = 1;
      view.pageable = data.webUrl.indexOf("webpage-open-3in1.php") !== -1;
      view.totalPages = data.totalFound
        ? Math.max(1, Math.ceil(Number(data.totalFound) / DOCUSKY_PAGE_SIZE))
        : null;
      view.label = [data.db, data.corpus && data.corpus !== data.db ? data.corpus : null,
                    data.query, data.totalFound ? data.totalFound + " 筆" : null]
        .filter(Boolean).join(" · ");
      mount();
    } else if (data && data.error) {
      showMessage("DocuSky 回傳了錯誤：", data.error);
    } else {
      showMessage(
        "這次查詢沒有可內嵌顯示的 DocuSky 網頁（多半是私人資料庫查詢，需要在瀏覽器另外登入 DocuSky）。",
        textBlock ? String(textBlock.text).slice(0, 500) : null
      );
    }
  }

  // --- host channel -----------------------------------------------------

  window.addEventListener("message", function (event) {
    var msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;

    if (msg.id === 1) {
      if (msg.error) {
        showMessage("這個 MCP 用戶端拒絕了 MCP Apps 交握：", JSON.stringify(msg.error));
        settled = true;
        return;
      }
      var result = msg.result || {};
      host.capabilities = result.hostCapabilities || {};
      host.context = result.hostContext || {};
      host.displayMode = host.context.displayMode || "inline";
      applyTheme(host.context);
      post({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} });
      // Ask for room: a retrieval page in a 200px-tall strip is unusable.
      post({
        jsonrpc: "2.0",
        method: "ui/notifications/size-changed",
        params: { height: INLINE_HEIGHT }
      });
      return;
    }

    if (msg.id && waiting[msg.id]) {
      var cb = waiting[msg.id];
      delete waiting[msg.id];
      if (!msg.error) cb(msg.result);
      return;
    }

    if (msg.method === "ui/notifications/tool-result") {
      handleToolResult(msg.params);
    } else if (msg.method === "ui/notifications/host-context-changed") {
      var ctx = msg.params || {};
      Object.keys(ctx).forEach(function (k) { host.context[k] = ctx[k]; });
      if (ctx.displayMode) host.displayMode = ctx.displayMode;
      applyTheme(host.context);
      if (view.base) renderBar();
    }
  });

  post({
    jsonrpc: "2.0",
    id: 1,
    method: "ui/initialize",
    params: {
      appInfo: APP_INFO,
      appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] },
      protocolVersion: PROTOCOL_VERSION
    }
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


# ---------------------------------------------------------------------------
# WordCloudLite (https://docusky.org.tw/docusky/docuTools/WordCloudLite/)
#
# Read from its source on 2026-09-12: the page accepts exactly two URL query
# parameters -- `url=<some.csv>` and `data=<name,value;name,value;...>`. Every
# other setting (title, backgroundColor, hideControlBar, ...) arrives only via
# `postMessage`, and its handler rejects any origin that is not docusky.org.tw
# itself, so a sandboxed MCP Apps iframe cannot use it. `url=` needs a CSV
# somewhere public, which a stdio MCP server has no way to host. That leaves
# `data=`, which is enough.
#
# Two things the page's own code forces on the caller, both verified live:
#
# * `data=` values stay JavaScript *strings* (the parser only does
#   `v.split(',')`), while the drawing code does `d3.max(data, d => d.value)`
#   and expects numbers -- d3 v5 compares strings lexicographically, so a set
#   like 100/90/9 makes "9" the maximum, every font size overshoots, and the
#   page renders BLANK. Zero-padding every value to the same width makes
#   lexicographic order match numeric order and fixes it ("090" < "100"), and
#   the later arithmetic (`d.value / maxValue`) coerces padded strings fine.
# * DocuSky's Apache answers 200 for a ~15 KB URL and 414 for ~24 KB, so the
#   built URL is trimmed (smallest terms first) to stay under the cap.
#
# Note the page deliberately draws a random subset when it is given many terms
# (see its `plotWordCloud`), so a cloud of ~20-40 terms is what reliably shows
# every word passed in.
# ---------------------------------------------------------------------------

WORDCLOUD_PAGE = "https://docusky.org.tw/docusky/docuTools/WordCloudLite/WordCloudLite.html"
WORDCLOUD_URL_LIMIT = 15000
WORDCLOUD_MAX_TERMS = 150


def build_wordcloud_url(
    terms: dict[str, float] | list[Any],
    max_terms: int = WORDCLOUD_MAX_TERMS,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Build a WordCloudLite URL for `terms`.

    Accepts either {"term": weight, ...} or a list of {"name","value"} /
    ("name", value) pairs. Returns (url, terms actually included, notes about
    anything adjusted or dropped). Raises ValueError when nothing is usable.
    """
    pairs = _normalize_terms(terms)
    notes: list[str] = []

    cleaned: dict[str, float] = {}
    dropped_empty = dropped_value = 0
    for name, value in pairs:
        name = " ".join(str(name).replace(",", " ").replace(";", " ").split())
        if not name:
            dropped_empty += 1
            continue
        try:
            weight = float(value)
        except (TypeError, ValueError):
            dropped_value += 1
            continue
        if weight <= 0:
            dropped_value += 1
            continue
        cleaned[name] = max(cleaned.get(name, 0.0), weight)

    if not cleaned:
        raise ValueError("No usable terms: each needs a non-empty name and a positive number.")
    if dropped_empty:
        notes.append(f"{dropped_empty} term(s) with an empty name were skipped.")
    if dropped_value:
        notes.append(f"{dropped_value} term(s) without a positive numeric value were skipped.")

    ordered = sorted(cleaned.items(), key=lambda kv: (-kv[1], kv[0]))
    if max_terms > 0 and len(ordered) > max_terms:
        notes.append(f"Kept the top {max_terms} of {len(ordered)} terms.")
        ordered = ordered[:max_terms]

    # Scale to positive integers: the page needs equal-width numeric strings.
    top = ordered[0][1]
    if any(float(v) != int(v) for _, v in ordered) or top < 1:
        scale = 999.0 / top
        weights = [max(1, round(v * scale)) for _, v in ordered]
        notes.append("Values were rescaled to whole numbers; relative sizes are unchanged.")
    else:
        weights = [int(v) for _, v in ordered]
    width = len(str(max(weights)))
    used = [
        {
            "name": name,
            "value": int(original) if float(original).is_integer() else original,
            "plotted": str(w).zfill(width),
        }
        for (name, original), w in zip(ordered, weights)
    ]

    url = _encode_wordcloud_url(used)
    while len(url) > WORDCLOUD_URL_LIMIT and len(used) > 1:
        used.pop()
        url = _encode_wordcloud_url(used)
    if len(used) < len(ordered):
        notes.append(
            f"{len(ordered) - len(used)} of the smallest term(s) were dropped to keep the "
            "URL within DocuSky's length limit."
        )
    if len(used) > 40:
        notes.append(
            "WordCloudLite draws a random subset when given many terms; pass roughly 20-40 "
            "terms if every word must appear."
        )
    return url, used, notes


def _normalize_terms(terms: dict[str, float] | list[Any]) -> list[tuple[Any, Any]]:
    """Flatten the shapes a caller might send into (name, value) pairs."""
    if isinstance(terms, str):
        terms = json.loads(terms)
    if isinstance(terms, dict):
        return list(terms.items())
    pairs: list[tuple[Any, Any]] = []
    for item in terms or []:
        if isinstance(item, dict):
            name = item.get("name", item.get("term", item.get("word")))
            value = item.get("value", item.get("count", item.get("weight")))
            pairs.append((name, value))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            pairs.append((item[0], item[1]))
        else:
            raise ValueError(f"Cannot read a term/value pair from: {item!r}")
    return pairs


def _encode_wordcloud_url(used: list[dict[str, Any]]) -> str:
    data = ";".join(f"{item['name']},{item['plotted']}" for item in used)
    return f"{WORDCLOUD_PAGE}?{urlencode({'data': data})}"
