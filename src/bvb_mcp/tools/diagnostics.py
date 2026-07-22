"""Diagnostic tools: datafeed server time and datafeed configuration.

Both read the BVB TradingView-UDF datafeed and exist mainly to confirm the
backend is reachable and to expose the instrument-type and resolution
vocabulary the other tools speak. There are no write tools here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings

_READ_ONLY = {"readOnlyHint": True}


def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None:
    """Register the diagnostic tools (all read-only) on *mcp*."""

    async def server_time() -> dict[str, Any]:
        """Get BVB's datafeed server time.

        Returns ``unix`` (server time in unix seconds) and ``iso`` (the same
        instant as an ISO 8601 UTC timestamp). Useful as a reachability check
        and to anchor ``from_``/``to`` windows for get_candles.
        """
        text = (await client.datafeed_text("/api/time")).strip()
        try:
            unix = int(text)
        except ValueError as exc:
            raise ToolError(f"unexpected /api/time response: {text!r}") from exc
        return {"unix": unix, "iso": datetime.fromtimestamp(unix, tz=UTC).isoformat()}

    async def datafeed_config() -> dict[str, Any]:
        """Get the datafeed configuration: instrument types and resolutions.

        Returns ``symbols_types`` (each ``{name, value}``, where ``value`` is
        the one-letter type code: S=Actiuni/shares, B=Obligatiuni/bonds,
        R=Drepturi/rights, U=Unitati de fond/fund units, T=Structurate, F=
        Futures, I=Indici/indices) and ``supported_resolutions`` (the datafeed's
        advertised resolution vocabulary).

        Note: the config advertises a bare ``"D"`` for daily, but the history
        endpoint requires ``"1D"`` — get_candles handles that translation, so
        pass its friendly ``resolution`` values rather than these raw codes.
        """
        data = await client.datafeed_json(
            "/api/config", params={"withNews": "false", "lang": settings.lang}
        )
        data = data or {}
        return {
            "symbols_types": data.get("symbols_types"),
            "supported_resolutions": data.get("supported_resolutions"),
        }

    mcp.tool(server_time, annotations=_READ_ONLY)
    mcp.tool(datafeed_config, annotations=_READ_ONLY)
