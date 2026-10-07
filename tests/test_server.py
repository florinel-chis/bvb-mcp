"""Server assembly tests: the full tool registry and the console entry point."""

from __future__ import annotations

import pytest
from fastmcp import Client

from bvb_mcp.server import build_server
from bvb_mcp.server import main as server_main

READ_TOOLS = frozenset(
    {
        "server_time",
        "datafeed_config",
        "get_symbol_info",
        "search_symbol",
        "get_candles",
        "list_instruments",
        "list_indices",
        "get_fundamentals",
        "financial_summary",
        "get_order_book",
    }
)


async def _tools(server) -> dict[str, object]:
    async with Client(server) as client:
        return {tool.name: tool for tool in await client.list_tools()}


async def test_build_server_registers_every_tool(settings) -> None:
    tools = await _tools(build_server(settings))
    assert set(tools) == READ_TOOLS


async def test_all_tools_are_read_only(settings) -> None:
    tools = await _tools(build_server(settings))
    for name, tool in tools.items():
        assert tool.annotations is not None and tool.annotations.readOnlyHint, name


def test_loopback_host_detection() -> None:
    from bvb_mcp.server import _is_loopback_host

    for host in ("127.0.0.1", "127.1.2.3", "::1", "localhost", "LocalHost", " 127.0.0.1 "):
        assert _is_loopback_host(host), host
    for host in ("0.0.0.0", "192.168.1.5", "10.0.0.1", "::", "example.com", ""):
        assert not _is_loopback_host(host), host


def test_http_refuses_non_loopback_bind_without_allow_remote(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["bvb-mcp", "--transport", "http", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit) as excinfo:
        server_main()
    assert excinfo.value.code == 2
    assert "--allow-remote" in capsys.readouterr().err


def test_help_exits_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["bvb-mcp", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        server_main()
    assert excinfo.value.code == 0
    assert "usage: bvb-mcp" in capsys.readouterr().out
