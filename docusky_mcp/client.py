"""Thin async client for the DocuSky Web API.

DocuSky (https://docusky.org.tw) exposes a JSON Web API under
``/DocuSky/webApi/*.php``.  The official front-end wraps it in jQuery widgets
(DocuWidgets); this module talks to the same endpoints directly.

Every endpoint answers with an envelope::

    {"code": 0, "message": <payload>}       # success
    {"code": <non-zero>, "message": "..."}  # failure

Authentication is a session cookie (``DocuSky_SID``) obtained from
``userLoginJson.php``.  Public ("OPEN") databases need no login at all.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://docusky.org.tw/DocuSky/webApi"
REQUESTER = "DocuSkyMCP"


class DocuSkyError(RuntimeError):
    """Raised when DocuSky answers with a non-zero code or unparsable body."""


_DECODER = json.JSONDecoder()


def loads_tolerant(text: str) -> Any:
    """Parse a DocuSky response body.

    Some endpoints emit PHP deprecation notices before the JSON payload, so a
    plain ``json.loads`` fails.  Scan for the first ``{`` that starts a valid
    JSON document, preferring one that actually looks like the API envelope.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fallback = None
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = _DECODER.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "code" in obj:
            return obj
        if fallback is None:
            fallback = obj
    if fallback is not None:
        return fallback
    raise DocuSkyError(f"DocuSky returned a non-JSON response: {text[:300]!r}")


_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"[ \t　]+")
_BLANKLINE_RE = re.compile(r"\n{3,}")


def strip_xml(value: str | None) -> str:
    """Turn a DocuXML fragment into readable plain text."""
    if not value:
        return ""
    text = re.sub(r"<(br|p|/p|lb)\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _BLANKLINE_RE.sub("\n\n", text)
    return text.strip()


class DocuSkyClient:
    """Async wrapper over the DocuSky Web API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._logged_in_as: str | None = None

    # -- plumbing ---------------------------------------------------------

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": f"{REQUESTER}/0.1"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._logged_in_as = None

    async def _call(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        client = await self._http()
        url = f"{self.base_url}/{endpoint}"
        query = {k: v for k, v in (params or {}).items() if v not in (None, "", False)}
        query.setdefault("requester", REQUESTER)
        try:
            if data is None:
                response = await client.get(url, params=query)
            else:
                response = await client.post(url, params=query, data=data)
        except httpx.HTTPError as exc:
            raise DocuSkyError(f"Cannot reach DocuSky ({url}): {exc}") from exc

        response.raise_for_status()
        payload = loads_tolerant(response.text)
        if not isinstance(payload, dict) or "code" not in payload:
            raise DocuSkyError(f"Unexpected DocuSky payload from {endpoint}: {payload!r}")
        if payload["code"] != 0:
            raise DocuSkyError(
                f"DocuSky {endpoint} failed (code {payload['code']}): {payload.get('message')}"
            )
        return payload.get("message")

    # -- authentication ---------------------------------------------------

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)

    async def login(self) -> str:
        if not self.has_credentials:
            raise DocuSkyError(
                "Private (USER) databases need a login. The user fills in their "
                "DocuSky account in the extension's own settings — never ask for "
                "the password in chat. Public databases work with target='OPEN'."
            )
        await self._call(
            "userLoginJson.php",
            data={"dsUname": self.username, "dsPword": self.password},
        )
        self._logged_in_as = self.username
        return self.username  # type: ignore[return-value]

    async def ensure_login(self, target: str) -> None:
        """Log in lazily — only private targets need a session."""
        if target.upper() == "USER" and self._logged_in_as is None:
            await self.login()

    async def logout(self) -> None:
        if self._logged_in_as is not None:
            await self._call("userLogoutJson.php")
            self._logged_in_as = None

    async def user_profile(self) -> Any:
        await self.ensure_login("USER")
        return await self._call("getUserProfileJson.php")

    # -- catalogue --------------------------------------------------------

    async def list_databases(
        self, target: str = "OPEN", include_friend_db: bool = False
    ) -> list[dict[str, Any]]:
        await self.ensure_login(target)
        message = await self._call(
            "getDbListJson.php",
            params={
                "target": target.upper(),
                "includeFriendDb": 1 if include_friend_db else None,
            },
        )
        return message or []

    async def list_corpora(
        self, db: str, target: str = "OPEN", include_friend_db: bool = False
    ) -> list[dict[str, Any]]:
        await self.ensure_login(target)
        message = await self._call(
            "getDbCorpusListJson.php",
            params={
                "target": target.upper(),
                "db": db,
                "includeFriendDb": 1 if include_friend_db else None,
            },
        )
        rows = message or []
        return [row for row in rows if not db or row.get("db") == db] or rows

    # -- retrieval --------------------------------------------------------

    async def query_documents(
        self,
        db: str,
        query: str = ".all",
        corpus: str = "[ALL]",
        page: int = 1,
        page_size: int = 20,
        target: str = "OPEN",
        fields_only: str | None = None,
        owner_username: str | None = None,
    ) -> dict[str, Any]:
        await self.ensure_login(target)
        return await self._call(
            "getQueryResultDocumentsJson.php",
            params={
                "target": target.upper(),
                "db": db,
                "corpus": corpus,
                "query": query,
                "page": page,
                "pageSize": page_size,
                "fieldsOnly": fields_only,
                "ownerUsername": owner_username,
            },
        )

    async def post_classification(
        self,
        db: str,
        query: str = ".all",
        corpus: str = "[ALL]",
        target: str = "OPEN",
        owner_username: str | None = None,
    ) -> dict[str, Any]:
        await self.ensure_login(target)
        return await self._call(
            "getQueryPostClassificationJson.php",
            params={
                "target": target.upper(),
                "db": db,
                "corpus": corpus,
                "query": query,
                "ownerUsername": owner_username,
            },
        )

    async def tag_analysis(
        self,
        db: str,
        query: str = ".all",
        corpus: str = "[ALL]",
        target: str = "OPEN",
        owner_username: str | None = None,
    ) -> dict[str, Any]:
        await self.ensure_login(target)
        return await self._call(
            "getQueryTagAnalysisJson.php",
            params={
                "target": target.upper(),
                "db": db,
                "corpus": corpus,
                "query": query,
                "ownerUsername": owner_username,
            },
        )
