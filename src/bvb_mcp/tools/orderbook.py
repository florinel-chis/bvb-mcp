"""Order book tool: the main-market top-5 order book for one instrument.

Read-only. The book is rendered on the instrument detail page's server-side
"Tranzactionare" tab, which a plain GET does not return: the tool GETs the page
for its ASP.NET form state, then replays the tab's postback (two requests). BVB
publishes this data delayed by 15 minutes.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings
from bvb_mcp.parse import parse_fundamentals, parse_order_book, parse_trading_tab_form

_DETAIL_PAGE = "/FinancialInstruments/Details/FinancialInstrumentsDetails.aspx"
_READ_ONLY = {"readOnlyHint": True}


def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None:
    """Register the order book tool (read-only) on *mcp*."""

    async def get_order_book(
        ticker: Annotated[
            str,
            Field(description='BVB ticker, e.g. "ATB", "TLV", or "SNP".'),
        ],
    ) -> dict[str, Any]:
        """Main-market (REGS) top-5 order book for a BVB instrument.

        Returns ticker, market ("REGS"), currency ("RON"), updated_at (the
        page's "Ultima actualizare" time, ISO 8601 Europe/Bucharest, or null),
        delayed (true when BVB marks the data as 15-minute delayed), bids
        (best/highest first) and asks (best/lowest first), each a list of up to
        five {price, volume} levels; volume is in shares. A side with no resting
        orders is an empty list. This is a delayed depth snapshot, not a live
        quote.
        """
        params = {"s": ticker}
        page = await client.web_html(_DETAIL_PAGE, params=params)
        if parse_fundamentals(page) is None:
            raise ToolError(f"no such BVB symbol: {ticker}")
        form = parse_trading_tab_form(page)
        if form is None:
            raise ToolError("detail page has no trading tab form (layout changed?)")
        trading = await client.web_postback(_DETAIL_PAGE, params=params, form=form)
        book = parse_order_book(trading)
        if book is None:
            raise ToolError("order book table not found (layout changed?)")
        return {
            "ticker": ticker.upper(),
            "market": "REGS",
            "currency": "RON",
            "updated_at": book["updated_at"],
            "delayed": 'class="delayedTimeImg"' in trading,
            "bids": book["bids"],
            "asks": book["asks"],
        }

    mcp.tool(get_order_book, annotations=_READ_ONLY)
