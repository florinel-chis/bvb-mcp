"""Symbol tools: metadata resolution and datafeed search.

Both read the BVB TradingView-UDF datafeed. There are no write tools here.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings

_READ_ONLY = {"readOnlyHint": True}


def _isin_from_description(description: str | None) -> str | None:
    """Pull the ISIN (last comma-separated token) out of a search description.

    Search descriptions look like ``"TLV, BANCA TRANSILVANIA S.A., ROTLVAACNOR1"``;
    the trailing token is the 12-character ISIN. Returns None if it does not
    look like an ISIN.
    """
    if not description:
        return None
    tail = description.rsplit(",", 1)[-1].strip()
    if len(tail) == 12 and tail[:2].isalpha() and tail.isalnum():
        return tail.upper()
    return None


def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None:
    """Register the symbol tools (all read-only) on *mcp*."""

    async def get_symbol_info(
        ticker: Annotated[
            str,
            Field(description='BVB ticker, e.g. "TLV", "SNP", or "BRD".'),
        ],
    ) -> dict[str, Any]:
        """Resolve one BVB ticker to its symbol metadata.

        Returns: ``ticker``, ``name`` (short name), ``description`` (issuer/full
        name), ``exchange`` (always "BVB"), ``type`` (e.g. "Shares"), ``session``
        (trading hours, e.g. "0700-1830"), ``timezone`` ("Europe/Bucharest"),
        ``currency_code`` (e.g. "RON"), ``sector``, ``industry``,
        ``has_intraday`` (whether intraday bars exist), ``supported_resolutions``,
        and ``pricescale`` (the datafeed's price scaling factor). Errors if the
        ticker does not resolve.
        """
        data = await client.datafeed_json("/api/symbols", params={"symbol": ticker})
        if not isinstance(data, dict) or data.get("s") == "error" or not data.get("name"):
            raise ToolError(f"no such BVB symbol: {ticker}")
        return {
            "ticker": data.get("ticker") or data.get("name"),
            "name": data.get("name"),
            "description": data.get("description"),
            "exchange": data.get("exchange"),
            "type": data.get("type"),
            "session": data.get("session"),
            "timezone": data.get("timezone"),
            "currency_code": data.get("currency_code"),
            "sector": data.get("sector"),
            "industry": data.get("industry"),
            "has_intraday": data.get("has_intraday"),
            "supported_resolutions": data.get("supported_resolutions"),
            "pricescale": data.get("pricescale"),
        }

    async def search_symbol(
        query: Annotated[
            str,
            Field(description='Free-text query matched against ticker and name, e.g. "TLV" or "banca".'),
        ],
        limit: Annotated[
            int,
            Field(description="Maximum number of results to return", ge=1),
        ] = 30,
    ) -> list:
        """Search the datafeed for symbols matching a query.

        Returns up to ``limit`` matches, each with ``symbol``, ``ticker``,
        ``full_name``, ``description`` (includes the ISIN as its trailing
        token), ``isin`` (extracted from the description for convenience),
        ``exchange``, and ``type`` (lowercase: "share", "bond", "structured",
        …).

        Note: the datafeed caps this search at roughly 30 results for broad
        queries, so it is a lookup aid, not a way to enumerate the full
        universe — use list_instruments (or list_indices) for that.
        """
        # The route only binds when query, type, exchange AND limit are all
        # present — omitting any one yields a 404 — so send all four even
        # though type/exchange are left empty.
        data = await client.datafeed_json(
            "/api/search",
            params={"query": query, "type": "", "exchange": "", "limit": limit},
        )
        results: list[dict[str, Any]] = []
        for item in (data or [])[:limit]:
            description = item.get("description")
            results.append(
                {
                    "symbol": item.get("symbol"),
                    "ticker": item.get("ticker"),
                    "full_name": item.get("full_name"),
                    "description": description,
                    "isin": _isin_from_description(description),
                    "exchange": item.get("exchange"),
                    "type": item.get("type"),
                }
            )
        return results

    mcp.tool(get_symbol_info, annotations=_READ_ONLY)
    mcp.tool(search_symbol, annotations=_READ_ONLY)
