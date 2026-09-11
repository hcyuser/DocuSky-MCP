"""MCP server exposing DocuSky (數位人文學術研究平台) to LLM clients.

Runs over stdio, so it works with Claude Code / Claude Desktop, Gemini CLI, or
any other MCP-capable client.

Environment variables
---------------------
DOCUSKY_USERNAME / DOCUSKY_PASSWORD
    Optional.  Only needed for private ("USER") databases.  Public ("OPEN")
    databases are queryable anonymously.
DOCUSKY_BASE_URL
    Override the Web API root (default: https://docusky.org.tw/DocuSky/webApi).
DOCUSKY_TIMEOUT
    Per-request timeout in seconds (default: 120).
"""

from __future__ import annotations

import json
import os
from typing import Any

try:  # MCP Python SDK >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # SDK 1.x, where the class was called FastMCP
    from mcp.server.fastmcp import FastMCP as _Server

try:  # MCP Apps (interactive UI) extension -- landed in the SDK during 2026.
    from mcp.server.apps import Apps, ResourceCsp

    _HAS_APPS = True
except ImportError:  # Older SDK: the tools below still work, just as plain text.
    Apps = None  # type: ignore[assignment,misc]
    ResourceCsp = None  # type: ignore[assignment,misc]
    _HAS_APPS = False

from .client import DocuSkyClient, DocuSkyError, strip_xml
from .credentials import credentials_path, load_credentials
from .ui import VIEWER_HTML, VIEWER_RESOURCE_URI, build_viewer_url

INSTRUCTIONS = """\
DocuSky is a digital-humanities platform hosting full-text databases of mostly
Chinese historical material (Buddhist/Daoist canons, gazetteers, biographies,
user-built corpora).

Typical flow:
  1. list_databases  -> pick a `db`
  2. list_corpora    -> pick a `corpus` (or keep "[ALL]")
  3. search_documents-> metadata + excerpt for each hit
  4. get_document    -> full text of one hit, by its `n` from the same search

`target` is "OPEN" for public databases (no login) or "USER" for the account's
own private databases (needs DOCUSKY_USERNAME / DOCUSKY_PASSWORD).

Query syntax: a bare string is a full-text phrase; `+term` requires a term,
`-term` excludes one (e.g. `醫 +方 -註`); `.all` matches every document.

For public ("OPEN") databases, search_documents, post_classification and
tag_analysis also return a `webUrl` pointing at the same query on
docusky.org.tw. MCP Apps-capable hosts render that inline as DocuSky's own
web page; other hosts can offer it to the user as a plain link instead.
"""

_credentials = load_credentials()
_client = DocuSkyClient(
    base_url=os.environ.get("DOCUSKY_BASE_URL", "https://docusky.org.tw/DocuSky/webApi"),
    username=_credentials.username,
    password=_credentials.password,
    timeout=float(os.environ.get("DOCUSKY_TIMEOUT", "120")),
)

MAX_PAGE_SIZE = 100
EMPTY_VALUES = {None, "", "-", "0"}


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _is_empty(value: Any) -> bool:
    """True for the placeholders DocuSky uses to mean "no data"."""
    if isinstance(value, (dict, list, tuple, str)):
        return not value or (isinstance(value, str) and value.strip() in EMPTY_VALUES)
    return value is None


def _clean(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop placeholder values, recursing into nested objects."""
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            value = _clean(value)
        if not _is_empty(value):
            out[key] = value
    return out


def _summarize_doc(entry: dict[str, Any], excerpt_chars: int) -> dict[str, Any]:
    info = entry.get("docInfo", {}) or {}
    body = strip_xml(info.get("docContentXml"))
    categories = [info.get(f"docCategoryL{i}") for i in (1, 2, 3)]
    record = {
        "n": entry.get("number"),
        "docId": info.get("docId"),
        "title": strip_xml(info.get("docTitleXml")) or info.get("docFilename"),
        "author": info.get("docAuthor"),
        "corpus": info.get("corpus"),
        "source": info.get("docSource"),
        "bookCode": info.get("docBookCode"),
        "compilation": info.get("docCompilation"),
        "category": " / ".join(c for c in categories if c and c != "-"),
        "time": _clean(info.get("timeInfo") or {}),
        "place": _clean(info.get("placeInfo") or {}),
        "filename": info.get("docFilename"),
        "contentChars": len(body),
    }
    if excerpt_chars > 0 and body:
        record["excerpt"] = body[:excerpt_chars] + ("…" if len(body) > excerpt_chars else "")
    return _clean(record)


def _error(exc: Exception) -> str:
    return _dump({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool implementations.
#
# These are plain functions, not yet decorated: three of them (search_documents,
# post_classification, tag_analysis) need to be bound to the MCP Apps `Apps()`
# extension *before* the MCPServer itself is constructed -- the SDK only reads
# an extension's tools/resources inside `MCPServer.__init__`, with no way to
# add more afterwards. The registration section at the bottom of this file
# decorates every function exactly once, in the right order.
# ---------------------------------------------------------------------------


async def list_databases(target: str = "OPEN", include_friend_db: bool = False) -> str:
    """List DocuSky databases available to this server.

    Args:
        target: "OPEN" for public databases, "USER" for the logged-in account's own.
        include_friend_db: Also list databases shared by DocuSky "friends" (USER only).
    """
    try:
        rows = await _client.list_databases(target=target, include_friend_db=include_friend_db)
    except DocuSkyError as exc:
        return _error(exc)

    databases = [
        _clean(
            {
                "db": row.get("db"),
                "owner": row.get("ownerUsername"),
                "category": row.get("dbCategory"),
                "corpora": [c for c in (row.get("corpusList") or "").split(";") if c],
                "created": row.get("dbTimeCreated"),
                "description": strip_xml(row.get("dbDescriptionXml")),
            }
        )
        for row in rows
    ]
    return _dump({"target": target.upper(), "count": len(databases), "databases": databases})


async def list_corpora(db: str, target: str = "OPEN", include_friend_db: bool = False) -> str:
    """List the corpora inside one database, with document counts.

    Args:
        db: Database title, exactly as returned by list_databases.
        target: "OPEN" or "USER".
        include_friend_db: Include databases shared by friends (USER only).
    """
    try:
        rows = await _client.list_corpora(db=db, target=target, include_friend_db=include_friend_db)
    except DocuSkyError as exc:
        return _error(exc)

    corpora = [
        _clean(
            {
                "corpus": row.get("corpus"),
                "docCount": row.get("docCount"),
                "attachmentCount": row.get("attachmentCount"),
                "created": row.get("timeCreated"),
                "status": row.get("dbStatusRemarks"),
            }
        )
        for row in rows
    ]
    return _dump({"db": db, "target": target.upper(), "corpora": corpora})


async def search_documents(
    db: str,
    query: str = ".all",
    corpus: str = "[ALL]",
    page: int = 1,
    page_size: int = 20,
    target: str = "OPEN",
    excerpt_chars: int = 300,
    owner_username: str | None = None,
) -> str:
    """Full-text search one DocuSky database; returns metadata plus a short excerpt per hit.

    Full document text is deliberately omitted — call get_document with a hit's
    `n` (and the same db/corpus/query/page_size) to read one in full.

    For a public ("OPEN") database, the result also carries a `webUrl` to the
    same search on docusky.org.tw — MCP Apps-capable hosts render it inline.

    Args:
        db: Database title.
        query: Search terms. `+term` requires, `-term` excludes, `.all` matches everything.
        corpus: Corpus title, or "[ALL]" for every corpus in the database.
        page: 1-based page number.
        page_size: Hits per page (1-100).
        target: "OPEN" or "USER".
        excerpt_chars: Characters of body text to preview per hit; 0 disables excerpts.
        owner_username: Owner of a friend-shared database, when applicable.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    try:
        message = await _client.query_documents(
            db=db,
            query=query,
            corpus=corpus,
            page=page,
            page_size=page_size,
            target=target,
            owner_username=owner_username,
        )
    except DocuSkyError as exc:
        return _error(exc)

    doc_list = message.get("docList") or []
    total = message.get("totalFound", 0)
    results = [_summarize_doc(entry, excerpt_chars) for entry in doc_list]
    return _dump(
        {
            "db": message.get("db", db),
            "corpus": message.get("corpus", corpus),
            "query": message.get("query", query),
            "totalFound": total,
            "page": message.get("page", page),
            "pageSize": message.get("pageSize", page_size),
            "returned": len(results),
            "results": results,
            "webUrl": build_viewer_url(db=db, corpus=corpus, query=query, target=target),
            "hint": (
                "Use get_document(db, query, result_number=<n>, corpus, page_size) "
                "with the same page_size to read a hit in full."
            ),
        }
    )


async def get_document(
    db: str,
    result_number: int,
    query: str = ".all",
    corpus: str = "[ALL]",
    target: str = "OPEN",
    page_size: int = 20,
    offset: int = 0,
    max_chars: int = 8000,
    include_raw_xml: bool = False,
    owner_username: str | None = None,
) -> str:
    """Fetch the full text of one search hit, identified by its position in the result set.

    `result_number` is the global 1-based rank of the document for this query —
    the `n` field of a search_documents hit. Pass the same db, query, corpus and
    page_size that produced it, or the ranking will not line up.

    Long documents are returned in slices: raise `offset` by `max_chars` to page
    through the body.

    Args:
        db: Database title.
        result_number: 1-based rank of the document within the query's results.
        query: The same query string used in search_documents.
        corpus: The same corpus used in search_documents.
        target: "OPEN" or "USER".
        page_size: The same page_size used in search_documents.
        offset: Character offset into the document body.
        max_chars: Maximum characters of body text to return.
        include_raw_xml: Also return the untouched DocuXML content.
        owner_username: Owner of a friend-shared database, when applicable.
    """
    if result_number < 1:
        return _dump({"error": "result_number is 1-based; it must be >= 1."})
    try:
        message = await _client.query_documents(
            db=db,
            query=query,
            corpus=corpus,
            page=result_number,
            page_size=1,
            target=target,
            owner_username=owner_username,
        )
    except DocuSkyError as exc:
        return _error(exc)

    doc_list = message.get("docList") or []
    if not doc_list:
        return _dump(
            {
                "error": f"No document at rank {result_number}.",
                "totalFound": message.get("totalFound", 0),
            }
        )

    entry = doc_list[0]
    info = entry.get("docInfo", {}) or {}
    body = strip_xml(info.get("docContentXml"))
    offset = max(0, offset)
    chunk = body[offset : offset + max(1, max_chars)]

    payload = {
        "db": message.get("db", db),
        "query": message.get("query", query),
        "resultNumber": result_number,
        "totalFound": message.get("totalFound", 0),
        "document": _summarize_doc(entry, excerpt_chars=0),
        "metadata": strip_xml(info.get("docMetadataXml")),
        "contentChars": len(body),
        "offset": offset,
        "returnedChars": len(chunk),
        "hasMore": offset + len(chunk) < len(body),
        "content": chunk,
    }
    if include_raw_xml:
        payload["rawContentXml"] = info.get("docContentXml")
    return _dump(payload)


async def post_classification(
    db: str,
    query: str = ".all",
    corpus: str = "[ALL]",
    target: str = "OPEN",
    owner_username: str | None = None,
) -> str:
    """Break a query's hits down by DocuSky's post-classification facets.

    Returns, per facet (corpus, period, place, category…), a distribution of
    [value, document count, hit count] — the quickest way to see how a term is
    spread across a database. Facet codes returned here (e.g. "COMP", "TP1")
    are also what twodim_analysis's dim1/dim2 arguments expect.

    For a public ("OPEN") database, the result also carries a `webUrl` to the
    same breakdown on docusky.org.tw — MCP Apps-capable hosts render it inline.

    Args:
        db: Database title.
        query: Search terms, or ".all" for the whole database.
        corpus: Corpus title, or "[ALL]".
        target: "OPEN" or "USER".
        owner_username: Owner of a friend-shared database, when applicable.
    """
    try:
        message = await _client.post_classification(
            db=db, query=query, corpus=corpus, target=target, owner_username=owner_username
        )
    except DocuSkyError as exc:
        return _error(exc)

    facets = {}
    for key, facet in (message.get("postClassification") or {}).items():
        facets[key] = {
            "title": facet.get("titleDisplay") or facet.get("title") or key,
            "distribution": [
                {"value": row[0], "docCount": row[1], "hitCount": row[2] if len(row) > 2 else None}
                for row in facet.get("distribution", [])
            ],
        }
    return _dump(
        {
            "db": message.get("db", db),
            "corpus": message.get("corpus", corpus),
            "query": message.get("query", query),
            "facets": facets,
            "webUrl": build_viewer_url(
                db=db, corpus=corpus, query=query, target=target, sp_type="postClassification"
            ),
        }
    )


async def tag_analysis(
    db: str,
    query: str = ".all",
    corpus: str = "[ALL]",
    target: str = "OPEN",
    owner_username: str | None = None,
) -> str:
    """Summarize the DocuXML tags (people, places, dates, custom markup) in a query's hits.

    Only meaningful for databases whose documents carry inline tagging; returns
    an empty result otherwise.

    For a public ("OPEN") database, the result also carries a `webUrl` to the
    same summary on docusky.org.tw — MCP Apps-capable hosts render it inline.

    Args:
        db: Database title.
        query: Search terms, or ".all" for the whole database.
        corpus: Corpus title, or "[ALL]".
        target: "OPEN" or "USER".
        owner_username: Owner of a friend-shared database, when applicable.
    """
    try:
        message = await _client.tag_analysis(
            db=db, query=query, corpus=corpus, target=target, owner_username=owner_username
        )
    except DocuSkyError as exc:
        return _error(exc)
    return _dump(
        {
            "db": message.get("db", db),
            "corpus": message.get("corpus", corpus),
            "query": message.get("query", query),
            "tagAnalysis": message.get("tagAnalysis"),
            "webUrl": build_viewer_url(
                db=db, corpus=corpus, query=query, target=target, sp_type="tagAnalysis"
            ),
        }
    )


async def twodim_analysis(
    db: str,
    dim1: str,
    dim2: str,
    query: str = ".all",
    corpus: str = "[ALL]",
    target: str = "OPEN",
    owner_username: str | None = None,
) -> str:
    """Cross-tabulate a query's hits by two DocuSky classification facets at once.

    EXPERIMENTAL: DocuSky added this endpoint on 2026-01-28, but live testing
    on 2026-09-11 found it rejects every dim1/dim2 pair tried so far —
    including facet codes taken straight from post_classification's own
    output, such as "COMP"/"TP1" — with `{"code": 1, "message": "Currently
    not support ..."}`. DocuSky's own front-end has not wired up a UI for it
    yet either. Call post_classification first to see which facet codes
    exist for a database, try them here, and expect DocuSky may still refuse
    the combination while this feature is unfinished on their end.

    Args:
        db: Database title.
        dim1: First classification facet code (a key from post_classification's
            "facets", e.g. "COMP" or "TP1").
        dim2: Second classification facet code to cross with the first.
        query: Search terms, or ".all" for the whole database.
        corpus: Corpus title, or "[ALL]".
        target: "OPEN" or "USER".
        owner_username: Owner of a friend-shared database, when applicable.
    """
    try:
        message = await _client.twodim_analysis(
            db=db,
            dim1=dim1,
            dim2=dim2,
            query=query,
            corpus=corpus,
            target=target,
            owner_username=owner_username,
        )
    except DocuSkyError as exc:
        return _error(exc)
    return _dump(
        {
            "db": db,
            "corpus": corpus,
            "query": query,
            "dim1": dim1,
            "dim2": dim2,
            "result": message,
        }
    )


async def check_login() -> str:
    """Report whether DocuSky credentials are configured and whether they work.

    Public databases need no login; run this only when private ("USER")
    databases are unreachable.
    """
    if not _client.has_credentials:
        return _dump(
            {
                "credentials": False,
                "loggedIn": False,
                "credentialsFile": str(credentials_path()),
                "message": (
                    "No credentials found. Public (OPEN) databases still work; "
                    "private (USER) ones need a login."
                ),
                "howToFix": (
                    "The user opens Settings -> Extensions -> DocuSky in Claude "
                    "Desktop, fills in their DocuSky username and password, and "
                    "restarts. Never ask for the password in chat."
                ),
            }
        )
    payload: dict[str, Any] = {
        "credentials": True,
        "username": _credentials.username,
        "source": _credentials.source,
    }
    if _credentials.source == "file":
        payload["credentialsFile"] = str(_credentials.path)
    if _credentials.warning:
        payload["warning"] = _credentials.warning
    try:
        payload["profile"] = await _client.user_profile()
    except DocuSkyError as exc:
        payload["loggedIn"] = False
        payload["error"] = str(exc)
        return _dump(payload)
    payload["loggedIn"] = True
    return _dump(payload)


# ---------------------------------------------------------------------------
# Registration.
#
# `Apps`-bound tools must be attached *before* `_Server(...)` is constructed
# (see the comment above the tool implementations). Everything else registers
# afterwards, same as before this feature existed.
# ---------------------------------------------------------------------------

apps = Apps() if _HAS_APPS else None
if apps is not None:
    apps.tool(resource_uri=VIEWER_RESOURCE_URI)(search_documents)
    apps.tool(resource_uri=VIEWER_RESOURCE_URI)(post_classification)
    apps.tool(resource_uri=VIEWER_RESOURCE_URI)(tag_analysis)
    apps.add_html_resource(
        VIEWER_RESOURCE_URI,
        VIEWER_HTML,
        title="DocuSky 網頁檢視",
        description="內嵌顯示 DocuSky 官方的查詢結果／分布統計／標記分析頁面",
        csp=ResourceCsp(frame_domains=["docusky.org.tw"]),
    )

mcp = _Server(
    "docusky",
    instructions=INSTRUCTIONS,
    version="0.2.0",
    extensions=[apps] if apps is not None else None,
)

mcp.tool()(list_databases)
mcp.tool()(list_corpora)
mcp.tool()(get_document)
mcp.tool()(twodim_analysis)
mcp.tool()(check_login)
if apps is None:
    # SDK predates MCP Apps: register these as plain text-only tools instead.
    mcp.tool()(search_documents)
    mcp.tool()(post_classification)
    mcp.tool()(tag_analysis)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
