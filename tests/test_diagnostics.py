"""Diagnostics domain tests: server_time and datafeed_config."""

from __future__ import annotations

import fastmcp
import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.tools import diagnostics

DATAFEED = "https://wapi.bvb.ro"


@respx.mock
async def test_server_time(make_server, settings, load_fixture) -> None:
    respx.get(f"{DATAFEED}/api/time").mock(
        return_value=Response(200, text=load_fixture("time.txt"))
    )
    server = make_server(settings, diagnostics.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("server_time", {})
    assert result.data["unix"] == 1784729782
    assert result.data["iso"].startswith("2026-")


@respx.mock
async def test_server_time_rejects_non_integer(make_server, settings) -> None:
    respx.get(f"{DATAFEED}/api/time").mock(return_value=Response(200, text="nope"))
    server = make_server(settings, diagnostics.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="unexpected /api/time"):
            await c.call_tool("server_time", {})


@respx.mock
async def test_datafeed_config(make_server, settings, load_fixture) -> None:
    route = respx.get(f"{DATAFEED}/api/config").mock(
        return_value=Response(200, text=load_fixture("config.json"))
    )
    server = make_server(settings, diagnostics.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("datafeed_config", {})
    types = {t["value"]: t["name"] for t in result.data["symbols_types"] if t["value"]}
    assert types["S"] == "Actiuni"
    assert types["I"] == "Indici"
    assert "1D" not in result.data["supported_resolutions"]  # config advertises bare "D"
    request = route.calls.last.request
    assert request.url.params["withNews"] == "false"
    assert request.url.params["lang"] == "ro"
