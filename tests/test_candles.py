"""Candles domain tests: OHLCV shape, the 1D quirk, params, no_data, errors."""

from __future__ import annotations

import fastmcp
import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.tools import candles

DATAFEED = "https://wapi.bvb.ro"
HISTORY = f"{DATAFEED}/api/history"


@respx.mock
async def test_get_candles_shape_and_required_params(make_server, settings, load_fixture) -> None:
    route = respx.get(HISTORY).mock(
        return_value=Response(200, text=load_fixture("history-tlv-1d.json"))
    )
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("get_candles", {"ticker": "TLV", "resolution": "1D", "countback": 30})
    assert len(result.data) == 30
    first = result.data[0]
    assert first["open"] == 33.3148
    assert first["volume"] == 872453
    assert first["time"].startswith("2026-")

    params = route.calls.last.request.url.params
    # All four "always required" history params are present, daily is 1D not D.
    assert params["symbol"] == "TLV"
    assert params["rs"] == "1D"
    assert params["ajust"] == "1"
    assert params["countback"] == "30"
    assert params["currencyCode"] == "RON"


@respx.mock
@pytest.mark.parametrize(
    ("resolution", "expected_rs"),
    [("d", "1D"), ("D", "1D"), ("1d", "1D"), ("w", "1W"), ("m", "1M"), ("60", "60")],
)
async def test_resolution_mapping(make_server, settings, resolution, expected_rs) -> None:
    route = respx.get(HISTORY).mock(return_value=Response(200, json={"s": "no_data"}))
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        await c.call_tool("get_candles", {"ticker": "TLV", "resolution": resolution})
    assert route.calls.last.request.url.params["rs"] == expected_rs


@respx.mock
async def test_adjusted_and_currency_flow_through(make_server, settings) -> None:
    route = respx.get(HISTORY).mock(return_value=Response(200, json={"s": "no_data"}))
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        await c.call_tool(
            "get_candles",
            {"ticker": "SNP", "adjusted": False, "currency": "EUR", "countback": 5},
        )
    params = route.calls.last.request.url.params
    assert params["ajust"] == "0"
    assert params["currencyCode"] == "EUR"


@respx.mock
async def test_countback_derived_from_window(make_server, settings) -> None:
    route = respx.get(HISTORY).mock(return_value=Response(200, json={"s": "no_data"}))
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        # A 10-day daily window should ask for ~10 bars.
        await c.call_tool(
            "get_candles",
            {"ticker": "TLV", "resolution": "1D", "from_": 1_781_136_000, "to": 1_781_136_000 + 10 * 86_400},
        )
    assert route.calls.last.request.url.params["countback"] == "10"


@respx.mock
async def test_no_data_returns_empty_list(make_server, settings) -> None:
    respx.get(HISTORY).mock(return_value=Response(200, json={"s": "no_data"}))
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("get_candles", {"ticker": "TLV"})
    assert result.data == []


@respx.mock
async def test_error_status_raises(make_server, settings) -> None:
    respx.get(HISTORY).mock(return_value=Response(200, json={"s": "error"}))
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="history unavailable for TLV"):
            await c.call_tool("get_candles", {"ticker": "TLV"})


async def test_unsupported_resolution_rejected(make_server, settings) -> None:
    server = make_server(settings, candles.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="unsupported resolution"):
            await c.call_tool("get_candles", {"ticker": "TLV", "resolution": "4H"})
