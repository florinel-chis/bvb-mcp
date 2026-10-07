"""Async HTTP layer over the BVB public backend.

One :class:`BvbClient` is shared by all tools. It talks to two hosts — the
TradingView-UDF datafeed at ``wapi.bvb.ro`` (JSON + a plain-text ``/time``) and
the WebForms market-list site at ``www.bvb.ro`` (HTML) — attaches the
browser-like ``User-Agent`` and a ``Referer: https://www.bvb.ro/`` to every
request, decodes responses, maps errors to :class:`fastmcp.exceptions.ToolError`,
and retries once on HTTP 429 honouring the ``Retry-After`` header (capped at
:data:`MAX_RETRY_AFTER` seconds). No auth token and no cookies are sent.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from bvb_mcp.config import Settings

DEFAULT_RETRY_AFTER = 2.0
MAX_RETRY_AFTER = 30.0

_TIMEOUT = 30.0
# BVB error bodies are ASP.NET Web API shapes such as {"Message": "..."}.
_ERROR_MESSAGE_KEYS = ("Message", "message", "errmsg", "error")


def _retry_after_seconds(response: httpx.Response) -> float:
    """Seconds to wait before the single 429 retry.

    Uses the ``Retry-After`` header when it is a finite, non-negative number of
    seconds, capped at :data:`MAX_RETRY_AFTER` so a hostile or buggy
    intermediary cannot stall a tool call indefinitely (``inf``/``nan`` and
    huge values are rejected); otherwise falls back to
    :data:`DEFAULT_RETRY_AFTER`.
    """
    raw = response.headers.get("Retry-After", "")
    try:
        seconds = float(raw)
    except ValueError:
        return DEFAULT_RETRY_AFTER
    if not math.isfinite(seconds) or seconds < 0:
        return DEFAULT_RETRY_AFTER
    return min(seconds, MAX_RETRY_AFTER)


def _error_message(response: httpx.Response) -> str:
    """Extract the backend's own error message from an error response.

    BVB error bodies are not covered by a single documented schema; the common
    shape carries a ``Message`` field. Falls back to the HTTP reason phrase so
    the message stays generic.
    """
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in _ERROR_MESSAGE_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return response.reason_phrase or "request failed"


class BvbClient:
    """Read-only client for the BVB datafeed and market-list site."""

    def __init__(self, settings: Settings) -> None:
        headers = {
            "User-Agent": settings.user_agent,
            "Referer": f"{settings.web_url}/",
            "Accept-Language": settings.lang,
        }
        self._datafeed = httpx.AsyncClient(
            base_url=settings.datafeed_url, headers=headers, timeout=_TIMEOUT
        )
        self._web = httpx.AsyncClient(
            base_url=settings.web_url, headers=headers, timeout=_TIMEOUT
        )

    async def _request(
        self,
        http: httpx.AsyncClient,
        path: str,
        params: dict[str, Any] | None,
        form: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET (or, when *form* is given, form-POST) with one retry on HTTP 429."""
        if params is not None:
            params = {key: value for key, value in params.items() if value is not None}
        method = "POST" if form is not None else "GET"
        response = await http.request(method, path, params=params or None, data=form)
        if response.status_code == 429:
            await asyncio.sleep(_retry_after_seconds(response))
            response = await http.request(method, path, params=params or None, data=form)
        if response.status_code >= 400:
            raise ToolError(f"HTTP {response.status_code}: {_error_message(response)}")
        return response

    async def datafeed_json(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        """GET a datafeed endpoint and return its decoded JSON body.

        Args:
            path: Datafeed path, e.g. ``"/api/config"`` or ``"/api/history"``.
            params: Query parameters; entries whose value is None are dropped.

        Raises:
            ToolError: for any non-2xx response (a 429 is retried once), or when
                the body is not valid JSON.
        """
        response = await self._request(self._datafeed, path, params)
        try:
            return response.json()
        except ValueError as exc:
            raise ToolError(f"invalid JSON from {path}") from exc

    async def datafeed_text(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> str:
        """GET a datafeed endpoint and return its body as text (e.g. ``/api/time``)."""
        response = await self._request(self._datafeed, path, params)
        return response.text

    async def web_html(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        """GET a market-list page from ``www.bvb.ro`` and return its HTML."""
        response = await self._request(self._web, path, params)
        return response.text

    async def web_postback(
        self, path: str, *, params: dict[str, Any] | None = None, form: dict[str, str]
    ) -> str:
        """POST an ASP.NET WebForms postback to ``www.bvb.ro`` and return its HTML.

        Used to switch a page to a server-side tab (e.g. the instrument detail
        page's "Tranzactionare" tab, which renders the order book).
        """
        response = await self._request(self._web, path, params, form)
        return response.text

    async def aclose(self) -> None:
        """Close both underlying HTTP connection pools."""
        await self._datafeed.aclose()
        await self._web.aclose()
