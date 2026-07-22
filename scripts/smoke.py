#!/usr/bin/env python3
"""Manual read-only smoke check against the live BVB backend.

Not part of the automated test suite and never run in CI. Usage:

    uv run python scripts/smoke.py

Requires only network access (BVB's backend is public and unauthenticated). The
script builds the server, calls a few read tools through the in-memory MCP
client, and prints only tool names and the shape of each result — field names
and item counts, never full values — so the terminal stays terse.
"""

from __future__ import annotations

import asyncio

from fastmcp import Client

from bvb_mcp.config import Settings
from bvb_mcp.server import build_server

SMOKE_CALLS = (
    ("server_time", {}),
    ("datafeed_config", {}),
    ("get_symbol_info", {"ticker": "TLV"}),
    ("search_symbol", {"query": "TLV"}),
    ("get_candles", {"ticker": "TLV", "resolution": "1D", "countback": 5}),
    ("list_instruments", {"market": "shares", "limit": 5}),
    ("list_indices", {}),
    ("get_fundamentals", {"ticker": "ATB"}),
    ("financial_summary", {"ticker": "TLV"}),
)


def _shape(payload: object) -> str:
    """Describe a tool result by structure only: field names and item counts."""
    if isinstance(payload, dict):
        if set(payload) == {"result"}:  # FastMCP wraps bare list results
            return _shape(payload["result"])
        return "fields: " + ", ".join(sorted(payload))
    if isinstance(payload, list):
        if not payload:
            return "empty list"
        return f"list of {len(payload)} items; item " + _shape(payload[0])
    return f"scalar ({type(payload).__name__})"


async def main() -> int:
    server = build_server(Settings.from_env())
    async with Client(server) as client:
        for name, args in SMOKE_CALLS:
            result = await client.call_tool(name, args)
            print(f"{name}: {_shape(result.structured_content)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
