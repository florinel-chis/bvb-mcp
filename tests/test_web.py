"""Playground page: served at / in HTTP mode, a self-contained MCP client."""

from __future__ import annotations

import re

from starlette.testclient import TestClient

from bvb_mcp.server import build_server


def _get(settings, path: str = "/", *, ui: bool = True):
    app = build_server(settings, ui=ui).http_app()
    with TestClient(app) as client:
        return client.get(path)


def test_playground_served_at_root(settings) -> None:
    response = _get(settings)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert "<title>bvb-mcp playground</title>" in page
    # It is a real MCP client speaking Streamable HTTP to the same server.
    for marker in (
        '"/mcp"',
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "mcp-session-id",
    ):
        assert marker in page, marker


def test_playground_is_self_contained(settings) -> None:
    # No external scripts, stylesheets, fonts or images: works offline/air-gapped.
    page = _get(settings).text
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', page)
    assert "@import" not in page


def test_playground_examples_use_registered_tools(settings) -> None:
    # Every example card names a tool the server actually registers.
    page = _get(settings).text
    examples = set(re.findall(r'tool:\s*"([a-z_]+)"', page))
    assert examples, "no examples found"
    registered = {
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
    assert examples <= registered, examples - registered


def test_no_ui_flag_disables_root(settings) -> None:
    assert _get(settings, ui=False).status_code == 404
