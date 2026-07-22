"""Symbols domain tests: get_symbol_info and search_symbol."""

from __future__ import annotations

import fastmcp
import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.tools import symbols

DATAFEED = "https://wapi.bvb.ro"


@respx.mock
async def test_get_symbol_info(make_server, settings, load_fixture) -> None:
    route = respx.get(f"{DATAFEED}/api/symbols").mock(
        return_value=Response(200, text=load_fixture("symbols-tlv.json"))
    )
    server = make_server(settings, symbols.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("get_symbol_info", {"ticker": "TLV"})
    assert result.data["ticker"] == "TLV"
    assert result.data["description"] == "BANCA TRANSILVANIA S.A."
    assert result.data["exchange"] == "BVB"
    assert result.data["type"] == "Shares"
    assert result.data["session"] == "0700-1830"
    assert result.data["timezone"] == "Europe/Bucharest"
    assert result.data["currency_code"] == "RON"
    assert result.data["has_intraday"] is True
    assert route.calls.last.request.url.params["symbol"] == "TLV"


@respx.mock
async def test_get_symbol_info_unknown(make_server, settings) -> None:
    respx.get(f"{DATAFEED}/api/symbols").mock(
        return_value=Response(200, json={"s": "error", "errmsg": "unknown_symbol"})
    )
    server = make_server(settings, symbols.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="no such BVB symbol: NOPE"):
            await c.call_tool("get_symbol_info", {"ticker": "NOPE"})


@respx.mock
async def test_search_symbol(make_server, settings, load_fixture) -> None:
    route = respx.get(f"{DATAFEED}/api/search").mock(
        return_value=Response(200, text=load_fixture("search-tlv.json"))
    )
    server = make_server(settings, symbols.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("search_symbol", {"query": "TLV", "limit": 4})
    assert len(result.data) == 4
    share = next(row for row in result.data if row["symbol"] == "TLV")
    assert share["type"] == "share"
    assert share["ticker"] == "TLV"
    # ISIN is extracted from the trailing token of the description.
    assert share["isin"] == "ROTLVAACNOR1"
    # /api/search 404s unless query, type, exchange AND limit are all present.
    sent = route.calls.last.request.url.params
    assert set(sent) >= {"query", "type", "exchange", "limit"}
    assert sent["query"] == "TLV"


@respx.mock
async def test_search_symbol_empty(make_server, settings) -> None:
    respx.get(f"{DATAFEED}/api/search").mock(return_value=Response(200, json=[]))
    server = make_server(settings, symbols.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("search_symbol", {"query": "zzz"})
    assert result.data == []
