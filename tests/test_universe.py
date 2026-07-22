"""Universe domain tests: list_instruments (scrape + aliases) and list_indices."""

from __future__ import annotations

import fastmcp
import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.tools import universe

WEB = "https://www.bvb.ro"


@respx.mock
async def test_list_instruments_shares(make_server, settings, load_fixture) -> None:
    route = respx.get(f"{WEB}/FinancialInstruments/Markets/Shares").mock(
        return_value=Response(200, text=load_fixture("shares.html"))
    )
    server = make_server(settings, universe.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("list_instruments", {"market": "shares", "limit": 5})
    assert len(result.data) == 5
    assert all(row["market"] == "shares" for row in result.data)
    tlv = next((row for row in result.data if row["ticker"] == "SNP"), None)
    assert tlv is not None
    assert tlv["isin"] == "ROSNPPACNOR9"
    assert tlv["name"] == "OMV PETROM S.A."
    assert route.called


@respx.mock
async def test_list_instruments_alias_maps_to_page(make_server, settings) -> None:
    route = respx.get(f"{WEB}/FinancialInstruments/Markets/FundUnits").mock(
        return_value=Response(200, text="<table id='gv'><tbody></tbody></table>")
    )
    server = make_server(settings, universe.register)
    async with fastmcp.Client(server) as c:
        # "etf" is an alias for the fund-units market page.
        result = await c.call_tool("list_instruments", {"market": "etf"})
    assert result.data == []
    assert route.called


async def test_list_instruments_unknown_market(make_server, settings) -> None:
    server = make_server(settings, universe.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="unknown market 'crypto'"):
            await c.call_tool("list_instruments", {"market": "crypto"})


@respx.mock
async def test_list_indices(make_server, settings, load_fixture) -> None:
    respx.get(f"{WEB}/FinancialInstruments/Indices/Overview").mock(
        return_value=Response(200, text=load_fixture("indices-overview.html"))
    )
    server = make_server(settings, universe.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("list_indices", {})
    symbols = [row["symbol"] for row in result.data]
    assert symbols[0] == "BET"
    assert "ROTX" in symbols
    assert len(symbols) == 13
    assert result.data[0]["isin"] == "ROXBSEI00005"
