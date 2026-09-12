"""MCP Apps (interactive UI) support for the DocuSky MCP server.

Wires `search_documents`, `post_classification`, `tag_analysis`,
`word_cloud` and `docugis_map` to a `ui://` resource so hosts that support the
MCP Apps extension (https://modelcontextprotocol.io/extensions/apps/overview)
render DocuSky's own web page inline, in a sandboxed iframe, instead of only
text.

There are two such resources. `VIEWER_HTML` embeds a DocuSky page that already
holds the data (a query result, a chart). `DOCUGIS_HTML` is for DocuGIS2,
which cannot be handed data through its URL at all: it embeds the empty tool
next to the TSV this server built, with a copy button, and the user pastes.

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
import re
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


# ---------------------------------------------------------------------------
# DocuGIS2 (https://docusky.org.tw/DocuSky/docuTools/DocuGIS2/)
#
# Unlike WordCloudLite, DocuGIS2 cannot be handed its data in a URL. All 56 of
# its scripts were read on 2026-09-12: not one parses `location.search` or
# `URLSearchParams`, and it registers no `message` listener, so a sandboxed
# iframe can neither pass it a payload nor call into it. What it does have is a
# paste box -- drop TSV into `#tsv`, press 匯入, and the rows land on the map --
# so this module builds the TSV and `DOCUGIS_HTML` puts a copy button next to
# the embedded tool. (It does honour one URL form, `index.html?f=<id>`, which
# pulls a dataset out of the registry file `gis/public/db.json`; publishing to
# that means writing into a shared community account and making the data public,
# so it is deliberately not used here.)
#
# What its importer accepts, measured live on 2026-09-12 by pasting TSV and
# reading back its grid:
#
# * A header row of `id name x y date text`, tab separated. `x` is WGS84
#   longitude and `y` latitude (the grid renames them lng/lat on import).
#   Columns beyond those six survive the import and show up in the popup.
# * The `date` column is unforgiving, and per row: `1887-01`, `1887-01-01`,
#   `1887/1/1`, `18870101`, even `-0200-01-01` (BCE) all import, but a bare
#   year (`1887`) or an empty cell makes the importer DROP that row, with a
#   single "Ignore incorrect data and continue loading correct data!" alert for
#   the whole file. Leave the `date` column out altogether, though, and every
#   row imports. Hence `include_dates` below: a bare year is padded to
#   `YYYY-01` rather than passed through, and a half-dated set drops the column
#   instead of silently losing the undated rows.
# ---------------------------------------------------------------------------

DOCUGIS_PAGE = "https://docusky.org.tw/DocuSky/docuTools/DocuGIS2/"
DOCUGIS_RESOURCE_URI = "ui://docusky/docugis.html"
DOCUGIS_MAX_ROWS = 2000

_DOCUGIS_CORE_COLUMNS = ("id", "name", "x", "y", "date", "text")
_DOCUGIS_ALIASES = {
    "id": ("id", "no", "num", "number", "seq", "序號", "編號"),
    "name": ("name", "place", "placename", "location", "title", "label",
             "地名", "名稱", "地點", "標題"),
    "x": ("x", "lon", "lng", "long", "longitude", "經度"),
    "y": ("y", "lat", "latitude", "緯度"),
    "date": ("date", "time", "year", "when", "日期", "時間", "年代", "年份"),
    "text": ("text", "desc", "description", "note", "content", "summary",
             "描述", "說明", "內容", "備註"),
}
_ALIAS_LOOKUP = {
    alias: canonical
    for canonical, aliases in _DOCUGIS_ALIASES.items()
    for alias in aliases
}

_YEAR_ONLY_RE = re.compile(r"^(-?)(\d{1,4})$")
_DATE_OK_RE = re.compile(r"^-?\d{1,4}[-/]\d{1,2}([-/]\d{1,2})?$|^\d{8}$")


def build_docugis_tsv(
    rows: list[Any] | dict[str, Any] | str,
    include_dates: bool | None = None,
    max_rows: int = DOCUGIS_MAX_ROWS,
) -> tuple[str, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Turn place rows into TSV that DocuGIS2's paste box will import.

    Returns (tsv, rows actually included, notes about anything adjusted,
    rows that were left out and why). Raises ValueError when nothing is usable.
    """
    records = _normalize_rows(rows)
    notes: list[str] = []
    skipped: list[dict[str, Any]] = []
    used: list[dict[str, Any]] = []
    extra_columns: list[str] = []
    flattened = swapped = padded_years = 0

    for position, record in enumerate(records, start=1):
        row = _canonical_row(record)
        name, hit = _flatten_cell(row.get("name"))
        flattened += hit
        if not name:
            skipped.append({"row": position, "reason": "沒有地名 (name)"})
            continue
        try:
            x = float(str(row.get("x", "")).strip())
            y = float(str(row.get("y", "")).strip())
        except (TypeError, ValueError):
            skipped.append({"row": position, "name": name, "reason": "x／y 不是數字"})
            continue
        # A lat/lon swap is the one coordinate mistake that is unambiguous:
        # latitude cannot exceed 90, so a y past that with a valid-looking x is
        # a swap, not a real point.
        if abs(y) > 90 and abs(x) <= 90:
            x, y = y, x
            swapped += 1
        if not (-180 <= x <= 180 and -90 <= y <= 90):
            skipped.append(
                {"row": position, "name": name, "reason": f"座標超出範圍 (x={x}, y={y})"}
            )
            continue

        date, date_state = _docugis_date(row.get("date"))
        if date_state == "padded":
            padded_years += 1
        elif date_state == "unusable":
            skipped_date = _flatten_cell(row.get("date"))[0]
            notes.append(f"第 {position} 列的日期「{skipped_date}」DocuGIS2 看不懂，已當成無日期。")

        entry: dict[str, Any] = {
            "id": _flatten_cell(row.get("id"))[0] or str(position),
            "name": name,
            "x": x,
            "y": y,
        }
        if date:
            entry["date"] = date
        text, hit = _flatten_cell(row.get("text"))
        flattened += hit
        if text:
            entry["text"] = text
        for key, value in row.items():
            if key in _DOCUGIS_CORE_COLUMNS:
                continue
            cell, hit = _flatten_cell(value)
            flattened += hit
            if not cell:
                continue
            column, hit = _flatten_cell(key)
            flattened += hit
            if column not in extra_columns:
                extra_columns.append(column)
            entry[column] = cell
        used.append(entry)

    if not used:
        raise ValueError(
            "No usable rows: each needs a name and numeric WGS84 coordinates "
            "(x = longitude, y = latitude)."
        )
    if skipped:
        notes.append(f"{len(skipped)} 列資料不完整，沒有放進 TSV（見 skipped）。")
    if swapped:
        notes.append(f"{swapped} 列的 x／y 顛倒了（緯度不可能超過 90），已對調。")
    if padded_years:
        notes.append(
            f"{padded_years} 列只給了年份。DocuGIS2 不吃純年份，會整列丟掉，"
            "所以補成該年 1 月（YYYY-01）。"
        )
    if max_rows > 0 and len(used) > max_rows:
        notes.append(f"只保留前 {max_rows} 列，共 {len(used)} 列。")
        used = used[:max_rows]

    dated = sum(1 for row in used if row.get("date"))
    if include_dates is None:
        # Auto: never trade rows for a timeline behind the user's back.
        use_dates = dated == len(used) and dated > 0
        if 0 < dated < len(used):
            notes.append(
                f"{len(used) - dated} 列沒有日期。DocuGIS2 只要 date 欄有空值就會整列丟掉，"
                "所以這次不輸出 date 欄（地圖完整，但沒有時間軸）。"
                "要時間軸請用 include_dates=true，代價是那幾列不會出現。"
            )
    else:
        use_dates = bool(include_dates)
        if use_dates and dated < len(used):
            notes.append(
                f"include_dates=true：{len(used) - dated} 列沒有日期，DocuGIS2 匯入時會丟掉它們"
                "（它只會跳一次「Ignore incorrect data」提示）。"
            )
        elif not use_dates and dated:
            notes.append("include_dates=false：日期已從 TSV 移除，時間軸不會有資料。")
    if not use_dates:
        for row in used:
            row.pop("date", None)
    if flattened:
        notes.append(f"{flattened} 個欄位裡的換行或 Tab 已換成空白（TSV 一列一筆）。")

    columns = ["id", "name", "x", "y"]
    if use_dates:
        columns.append("date")
    if any(row.get("text") for row in used):
        columns.append("text")
    columns.extend(extra_columns)
    return _encode_docugis_tsv(columns, used), used, notes, skipped


def _normalize_rows(rows: list[Any] | dict[str, Any] | str) -> list[dict[str, Any]]:
    """Flatten the shapes a caller might send into per-place dicts."""
    if isinstance(rows, str):
        rows = json.loads(rows)
    if isinstance(rows, dict):
        # {"臺北": {"x": ..., "y": ...}, ...}
        out = []
        for name, value in rows.items():
            record = dict(value) if isinstance(value, dict) else {"x": value}
            record.setdefault("name", name)
            out.append(record)
        return out
    normalized: list[dict[str, Any]] = []
    for item in rows or []:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            keys = ("name", "x", "y", "date", "text")
            normalized.append(dict(zip(keys, item)))
        else:
            raise ValueError(f"Cannot read a place row from: {item!r}")
    if not normalized:
        raise ValueError("No rows given: each needs a name and WGS84 x/y coordinates.")
    return normalized


def _canonical_row(record: dict[str, Any]) -> dict[str, Any]:
    """Rename known column aliases (lng -> x, 地名 -> name, ...), keep the rest."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        label = str(key).strip()
        canonical = _ALIAS_LOOKUP.get(label.lower().replace("_", "").replace(" ", ""))
        if canonical:
            out.setdefault(canonical, value)
        elif label:
            out.setdefault(label, value)
    return out


def _flatten_cell(value: Any) -> tuple[str, int]:
    """Squeeze a value onto one TSV line; also report whether that changed it."""
    if value is None:
        return "", 0
    text = str(value)
    hit = 1 if ("\t" in text or "\n" in text or "\r" in text) else 0
    return " ".join(text.split()), hit


def _docugis_date(value: Any) -> tuple[str | None, str | None]:
    """Normalize a date to something DocuGIS2's importer accepts, or None."""
    text = _flatten_cell(value)[0]
    if not text:
        return None, None
    year_only = _YEAR_ONLY_RE.match(text)
    if year_only:
        sign, digits = year_only.groups()
        return f"{sign}{int(digits):04d}-01", "padded"
    if _DATE_OK_RE.match(text):
        return text, None
    return None, "unusable"


def _coord(value: float) -> str:
    """Six decimals is ~0.1 m; trim the zeros that adds to round numbers."""
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _encode_docugis_tsv(columns: list[str], used: list[dict[str, Any]]) -> str:
    lines = ["\t".join(columns)]
    for row in used:
        cells = []
        for column in columns:
            value = row.get(column, "")
            cells.append(_coord(value) if column in ("x", "y") else str(value))
        lines.append("\t".join(cells))
    return "\n".join(lines)


# The DocuGIS2 viewer. Same MCP Apps handshake as VIEWER_HTML above, but the
# page it embeds starts empty: the data travels through the user's clipboard,
# so the TSV sits above the frame with a copy button and three steps.
#
# It also refuses to embed DocuGIS2 under a strict sandbox. Measured 2026-09-12
# with the two sandboxes side by side against the real page: with
# `allow-same-origin` DocuGIS2 loads normally, without it the page never gets
# past its loading spinner (an opaque origin makes its storage calls throw).
# A frame stuck on a spinner is worse than no frame, so that case shows the TSV
# and an "open in browser" button instead.
#
# Two more things the embedded page does differently, both seen 2026-09-12 in a
# replay of the reference host and reflected in the steps the viewer prints:
# it starts with its left menu collapsed (a real browser tab opens with the menu
# out), so the first step is the ⇥ button at the map's top-left; and it comes up
# in English, hence the bilingual button names.
DOCUGIS_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>DocuGIS2 地圖</title>
<style>
  :root { color-scheme: light dark; --fg: #1a1a1a; --bg: #fff; --bar: #f3f4f6; --line: #d8dade; }
  body.theme-dark { --fg: #e6e6e6; --bg: #1e1e1e; --bar: #2a2b2e; --line: #3a3b3f; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; flex-direction: column; background: var(--bg); color: var(--fg);
    font: 13px/1.5 -apple-system, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
  }
  #bar {
    display: flex; align-items: center; gap: 6px; flex: 0 0 auto; flex-wrap: wrap;
    padding: 5px 8px; background: var(--bar); border-bottom: 1px solid var(--line);
    font-size: 12px;
  }
  #label { opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 45%; }
  .spacer { flex: 1 1 auto; }
  button {
    font: inherit; color: inherit; background: transparent;
    border: 1px solid var(--line); border-radius: 5px; padding: 2px 8px; cursor: pointer;
  }
  button:hover:not(:disabled) { background: rgba(127, 127, 127, 0.16); }
  button.primary { border-color: #3b6fd4; color: #3b6fd4; font-weight: 600; }
  #steps { flex: 0 0 auto; padding: 4px 10px; font-size: 11px; opacity: 0.8;
           background: var(--bar); border-bottom: 1px solid var(--line); }
  #notes { flex: 0 0 auto; padding: 0 10px 4px; font-size: 11px; opacity: 0.8;
           background: var(--bar); border-bottom: 1px solid var(--line); }
  #notes ul { margin: 4px 0 0; padding-left: 18px; }
  #tsv {
    flex: 0 0 auto; width: 100%; box-sizing: border-box; height: 96px; resize: vertical;
    border: 0; border-bottom: 1px solid var(--line); padding: 6px 10px; background: var(--bg);
    color: var(--fg); white-space: pre; overflow: auto; tab-size: 12;
    font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, "Cascadia Mono", monospace;
  }
  #frame { flex: 1 1 auto; border: 0; width: 100%; min-height: 320px; background: #fff; }
  .msg { margin: auto; padding: 24px; text-align: center; max-width: 34em; }
  .msg code { display: block; margin-top: 8px; white-space: pre-wrap; word-break: break-all;
              opacity: 0.75; font-size: 12px; }
</style>
</head>
<body>
<div id="root" class="msg">正在準備 DocuGIS2…</div>
<script>
(function () {
  "use strict";

  // Wire format: https://github.com/modelcontextprotocol/ext-apps
  //              /blob/main/specification/2026-01-26/apps.mdx
  var PROTOCOL_VERSION = "2026-01-26";
  var APP_INFO = { name: "docusky-docugis", version: "0.4.0", title: "DocuGIS2 地圖" };
  var INLINE_HEIGHT = 760;

  var nextId = 2;                 // id 1 is the ui/initialize request
  var waiting = {};               // JSON-RPC id -> callback
  var host = { capabilities: {}, context: {}, displayMode: "inline" };
  var state = { tsv: "", label: "DocuGIS2", notes: [], url: null };
  var els = null;
  var settled = false;

  // Sandbox flags are inherited by the nested docusky.org.tw frame. Without
  // `allow-same-origin` that frame lives in an opaque origin, where DocuGIS2
  // hangs on its loading spinner forever (verified 2026-09-12). Storage
  // throwing is the same signal, so probe it and skip the embed in that case.
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

  function button(text, onClick, title) {
    var el = document.createElement("button");
    el.textContent = text;
    if (title) el.title = title;
    el.addEventListener("click", onClick);
    return el;
  }

  // --- clipboard --------------------------------------------------------
  // A sandboxed iframe often has neither the async clipboard API nor the
  // clipboard-write permission, so fall back to execCommand and, failing that,
  // leave the TSV selected and let the user press the shortcut themselves.

  function copyTsv() {
    var done = function (ok) {
      els.copy.textContent = ok ? "✓ 已複製，去下面貼上" : "請按 ⌘C／Ctrl+C 複製";
      setTimeout(function () { els.copy.textContent = "⧉ 複製 TSV"; }, 4000);
    };
    els.tsv.focus();
    els.tsv.select();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(state.tsv).then(function () { done(true); },
                                                    function () { done(execCopy()); });
      return;
    }
    done(execCopy());
  }

  function execCopy() {
    try { return document.execCommand("copy"); } catch (e) { return false; }
  }

  // --- rendering --------------------------------------------------------

  function mount() {
    document.body.innerHTML = "";

    var bar = document.createElement("div");
    bar.id = "bar";

    var steps = document.createElement("div");
    steps.id = "steps";
    steps.textContent = strictSandbox
      ? "這個用戶端把內嵌網頁鎖在最嚴格的沙箱裡，DocuGIS2 在裡面載不起來。"
        + "請按「瀏覽器開啟 DocuGIS2」，複製下面的 TSV，在左側選單點「匯入資料 Import Data」，"
        + "貼到右邊的貼上框，再按［匯入 Import］。"
      : "① 按上方「複製 TSV」 → ② 下方 DocuGIS2 按地圖左上角的 ⇥ 打開選單（內嵌時預設是收起來的），"
        + "點「1.2 匯入資料 Import Data」 → ③ 在右邊的貼上框按 ⌘V／Ctrl+V 貼上，"
        + "按［匯入 Import］，地點就會出現在地圖上。";

    var tsv = document.createElement("textarea");
    tsv.id = "tsv";
    tsv.readOnly = true;
    tsv.spellcheck = false;
    tsv.value = state.tsv;
    tsv.title = "DocuGIS2 匯入用的 TSV";
    // With no frame below it, the TSV is the only thing on the page: let it
    // have the room instead of leaving a blank half.
    if (strictSandbox) tsv.style.flex = "1 1 auto";

    document.body.appendChild(bar);
    document.body.appendChild(steps);
    if (state.notes.length) document.body.appendChild(buildNotes());
    document.body.appendChild(tsv);

    var frame = null;
    if (!strictSandbox) {
      frame = document.createElement("iframe");
      frame.id = "frame";
      frame.title = "DocuGIS2";
      frame.src = state.url;
      document.body.appendChild(frame);
    }

    els = { bar: bar, tsv: tsv, frame: frame, copy: null };
    renderBar();
  }

  function buildNotes() {
    var box = document.createElement("details");
    box.id = "notes";
    var head = document.createElement("summary");
    head.textContent = "整理資料時做了 " + state.notes.length + " 項調整";
    box.appendChild(head);
    var list = document.createElement("ul");
    state.notes.forEach(function (note) {
      var item = document.createElement("li");
      item.textContent = note;
      list.appendChild(item);
    });
    box.appendChild(list);
    return box;
  }

  function renderBar() {
    if (!els) return;
    var bar = els.bar;
    bar.innerHTML = "";

    var label = document.createElement("span");
    label.id = "label";
    label.textContent = state.label;
    bar.appendChild(label);

    els.copy = button("⧉ 複製 TSV", copyTsv);
    els.copy.className = "primary";
    bar.appendChild(els.copy);

    var spacer = document.createElement("span");
    spacer.className = "spacer";
    bar.appendChild(spacer);

    if (!strictSandbox
        && (host.context.availableDisplayModes || []).indexOf("fullscreen") !== -1) {
      bar.appendChild(button(host.displayMode === "fullscreen" ? "⤡ 結束全螢幕" : "⤢ 全螢幕",
        function () {
          var mode = host.displayMode === "fullscreen" ? "inline" : "fullscreen";
          request("ui/request-display-mode", { mode: mode }, function (result) {
            if (result && result.mode) { host.displayMode = result.mode; renderBar(); }
          });
        }));
    }
    if (host.capabilities.openLinks) {
      bar.appendChild(button("↗ 瀏覽器開啟 DocuGIS2", function () {
        request("ui/open-link", { url: state.url });
      }));
    }
    if (els.frame) {
      bar.appendChild(button("⟳", function () {
        els.frame.src = state.url;
      }, "重新載入 DocuGIS2（會清掉已匯入的資料）"));
    }
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
    if (data && typeof data.result === "string" && !data.tsv) {
      try { data = JSON.parse(data.result); } catch (e) { /* keep what we have */ }
    }

    if (data && data.tsv) {
      state.tsv = data.tsv;
      state.notes = data.notes || [];
      state.url = data.webUrl || "https://docusky.org.tw/DocuSky/docuTools/DocuGIS2/";
      state.label = [data.title, data.rowCount ? data.rowCount + " 個地點" : null]
        .filter(Boolean).join(" · ") || "DocuGIS2";
      mount();
    } else if (data && data.error) {
      showMessage("沒有可以上圖的資料：", data.error);
    } else {
      showMessage(
        "這次沒有拿到可匯入 DocuGIS2 的 TSV。",
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
      if (els) renderBar();
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
      showMessage("尚未收到資料。這個 MCP 用戶端可能不支援 MCP Apps 內嵌顯示。");
    }
  }, 8000);
})();
</script>
</body>
</html>
"""
