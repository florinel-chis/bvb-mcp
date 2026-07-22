"""Universe tools: the full instrument list and the index universe.

The datafeed ``/api/search`` is server-capped, so these tools instead scrape
the server-rendered ``www.bvb.ro`` market-list pages. There are no write tools
here.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings
from bvb_mcp.parse import parse_indices, parse_market_rows

# Canonical market key -> the WebForms market-list page that lists it. These are
# the markets BVB actually publishes a scrapeable page for (verified live). The
# datafeed also defines R=Drepturi/rights, but BVB has no standalone rights
# market page, and indices have their own tool (list_indices).
_MARKET_PAGES: dict[str, str] = {
    "shares": "/FinancialInstruments/Markets/Shares",
    "bonds": "/FinancialInstruments/Markets/Bonds",
    "fund-units": "/FinancialInstruments/Markets/FundUnits",
    "warrants": "/FinancialInstruments/Markets/Warrants",
    "certificates": "/FinancialInstruments/Markets/Certificates",
}

# Friendly synonyms accepted for the ``market`` argument.
_MARKET_ALIASES: dict[str, str] = {
    "share": "shares",
    "bond": "bonds",
    "fund-unit": "fund-units",
    "fundunits": "fund-units",
    "funds": "fund-units",
    "etf": "fund-units",
    "etfs": "fund-units",
    "warrant": "warrants",
    "certificate": "certificates",
    "structured": "certificates",
}

_INDICES_PAGE = "/FinancialInstruments/Indices/Overview"

_READ_ONLY = {"readOnlyHint": True}


def _resolve_market(market: str) -> str:
    """Normalise a market argument to a canonical key, or raise."""
    key = market.strip().lower().replace("_", "-")
    key = _MARKET_ALIASES.get(key, key)
    if key not in _MARKET_PAGES:
        valid = ", ".join(sorted(_MARKET_PAGES))
        raise ToolError(f"unknown market {market!r}; valid markets: {valid}")
    return key


def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None:
    """Register the universe tools (all read-only) on *mcp*."""

    async def list_instruments(
        market: Annotated[
            str,
            Field(
                description=(
                    "Instrument market: 'shares', 'bonds', 'fund-units' (ETFs), "
                    "'warrants', or 'certificates' ('structured'). For indices "
                    "use list_indices."
                )
            ),
        ] = "shares",
        limit: Annotated[
            int,
            Field(description="Maximum number of instruments to return", ge=1),
        ] = 500,
    ) -> list:
        """List the instrument universe for a BVB market.

        Scrapes the exchange's market-list page (the datafeed search is capped
        and unsuitable for enumeration). Returns up to ``limit`` instruments,
        each ``{ticker, isin, name, market}`` — ``isin`` is the 12-character
        BVB ISIN (or null if the page omits it), ``name`` is the issuer, and
        ``market`` echoes the normalised market key.
        """
        key = _resolve_market(market)
        html = await client.web_html(_MARKET_PAGES[key])
        rows = parse_market_rows(html)
        results: list[dict[str, Any]] = []
        for row in rows[:limit]:
            results.append({**row, "market": key})
        return results

    async def list_indices(
        limit: Annotated[
            int,
            Field(description="Maximum number of indices to return", ge=1),
        ] = 50,
    ) -> list:
        """List the BVB index universe (BET, BET-TR, BET-FI, ROTX, …).

        Scrapes the indices overview page. Returns up to ``limit`` indices, each
        ``{symbol, name, isin}``. Every index's ``symbol`` is returned; ``name``
        and ``isin`` are populated only for indices BVB renders a server-side
        profile for (others load via client-side tabs) and are otherwise null.
        Pass a ``symbol`` to get_candles to chart an index.
        """
        html = await client.web_html(_INDICES_PAGE)
        return parse_indices(html)[:limit]

    mcp.tool(list_instruments, annotations=_READ_ONLY)
    mcp.tool(list_indices, annotations=_READ_ONLY)
