"""Fundamentals domain tests: get_fundamentals and financial_summary."""

from __future__ import annotations

import fastmcp
import respx
from httpx import Response

from bvb_mcp.tools import fundamentals

DATAFEED = "https://wapi.bvb.ro"
WEB = "https://www.bvb.ro"

# 3 daily closes (ascending), enough for financial_summary's price block.
_HISTORY = {"t": [1784505600, 1784592000, 1784678400], "o": [1, 1, 1], "h": [2, 2, 2],
            "l": [1, 1, 1], "c": [10.0, 11.0, 12.0], "v": [1, 1, 1], "s": "ok"}


@respx.mock
async def test_get_fundamentals(make_server, settings, load_fixture) -> None:
    route = respx.get(url__regex=rf"{WEB}/FinancialInstruments/Details/.*").mock(
        return_value=Response(200, text=load_fixture("detail-atb.html"))
    )
    server = make_server(settings, fundamentals.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("get_fundamentals", {"ticker": "ATB"})
    d = result.data
    assert d["ticker"] == "ATB"
    assert d["name"] == "ANTIBIOTICE S.A."
    assert d["isin"] == "ROATBIACNOR9"
    assert d["segment"] == "Principal"
    assert d["market_cap"] == 1463516927.20
    assert d["per"] == 28.27
    assert d["pbv"] == 1.57
    assert d["eps"] == 0.08
    assert d["div_yield"] == 0.94
    assert d["dividend"] == 0.020557
    assert d["dividend_year"] == 2024
    assert d["shares_outstanding"] == 671338040
    assert d["first_trade_date"] == "1997-04-16"
    # Ownership: TOTAL excluded, top holder is the Ministry of Health.
    assert len(d["shareholders"]) == 4
    assert d["shareholders"][0]["percent"] == 53.0172
    assert "MINISTERUL SANATATII" in d["shareholders"][0]["name"]
    # The tool sends the ticker as the ?s= param with browser headers.
    assert route.calls.last.request.url.params["s"] == "ATB"


@respx.mock
async def test_get_fundamentals_unknown(make_server, settings) -> None:
    respx.get(url__regex=rf"{WEB}/FinancialInstruments/Details/.*").mock(
        return_value=Response(200, text="<html><body>no such symbol</body></html>")
    )
    server = make_server(settings, fundamentals.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("get_fundamentals", {"ticker": "NOPE"}, raise_on_error=False)
    assert result.is_error


@respx.mock
async def test_financial_summary(make_server, settings, load_fixture) -> None:
    respx.get(url__regex=rf"{WEB}/FinancialInstruments/Details/.*").mock(
        return_value=Response(200, text=load_fixture("detail-atb.html"))
    )
    respx.get(f"{DATAFEED}/api/history").mock(return_value=Response(200, json=_HISTORY))
    server = make_server(settings, fundamentals.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("financial_summary", {"ticker": "ATB"})
    d = result.data
    assert d["ticker"] == "ATB"
    assert d["fundamentals"]["per"] == 28.27
    assert d["price"]["last_close"] == 12.0
    assert d["price"]["high_52w"] == 12.0
    assert d["price"]["low_52w"] == 10.0
    assert "multi-year" in d["note"]
