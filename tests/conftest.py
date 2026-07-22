"""Shared test fixtures.

The canonical pattern for testing a domain module end to end — in-memory
FastMCP client on the outside, respx-mocked HTTP on the inside::

    import fastmcp
    import respx
    from httpx import Response

    from bvb_mcp.tools import symbols


    @respx.mock
    async def test_get_symbol_info(make_server, settings, load_fixture):
        respx.get("https://wapi.bvb.ro/api/symbols").mock(
            return_value=Response(200, text=load_fixture("symbols-tlv.json"))
        )
        server = make_server(settings, symbols.register)
        async with fastmcp.Client(server) as c:
            result = await c.call_tool("get_symbol_info", {"ticker": "TLV"})
        assert result.data["ticker"] == "TLV"

Assert on ``result.data`` (the deserialized structured output) and on the
respx route's captured request: the browser-like ``User-Agent`` and the
``Referer`` header must be present and the query must match exactly.

For ``result.data`` items of list tools to be plain, subscriptable dicts, the
tool must use a bare ``list`` (or ``list[Any]``) return annotation — FastMCP's
client deserializes typed dict items (``list[dict[str, Any]]``) into opaque root
models.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastmcp import FastMCP

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings

RegisterFn = Callable[[FastMCP, BvbClient, Settings], None]

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings() -> Settings:
    """Default settings: the live BVB hosts (respx intercepts the requests)."""
    return Settings()


@pytest.fixture
def load_fixture() -> Callable[[str], str]:
    """Return a function that reads a captured response fixture as text."""

    def _load(name: str) -> str:
        return (_FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def make_server() -> Callable[[Settings, RegisterFn], FastMCP]:
    """Build a bare server with exactly one domain's tools registered."""

    def _make(settings: Settings, register_fn: RegisterFn) -> FastMCP:
        mcp = FastMCP("bvb-mcp-test")
        client = BvbClient(settings)
        register_fn(mcp, client, settings)
        return mcp

    return _make
