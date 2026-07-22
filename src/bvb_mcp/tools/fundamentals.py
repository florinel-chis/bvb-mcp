"""Fundamentals tools: company details + valuation snapshot, and a one-call
summary for a Buffett-style analysis.

Both tools are read-only. Data is scraped from the instrument detail page's
server-rendered tables (identity, "Indicatori bursieri", issue info, ownership).
BVB publishes no multi-year income/balance/cash-flow statements as structured
data — only these current-snapshot ratios plus PDF reports — so this is a
snapshot, not a historical track record. The financial_summary tool pairs the
snapshot with a price summary derived from the datafeed so an analysis has every
input in one call; the actual reasoning is left to the caller.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings
from bvb_mcp.parse import parse_fundamentals

_DETAIL_PAGE = "/FinancialInstruments/Details/FinancialInstrumentsDetails.aspx"
_READ_ONLY = {"readOnlyHint": True}

# ~5 trading years of daily bars for the price summary.
_SUMMARY_BARS = 1300
_YEAR_BARS = 252


async def _fundamentals(client: BvbClient, ticker: str) -> dict[str, Any]:
    """Fetch + parse the detail page, or raise ToolError for an unknown ticker."""
    html = await client.web_html(_DETAIL_PAGE, params={"s": ticker})
    data = parse_fundamentals(html)
    if data is None:
        raise ToolError(f"no such BVB symbol: {ticker}")
    return data


async def _price_summary(client: BvbClient, ticker: str) -> dict[str, Any]:
    """Derive a price snapshot (last close, 52w range, 1y/5y change) from the
    datafeed's daily history. Returns empty-ish fields when history is absent."""
    to_ts = int(time.time())
    data = await client.datafeed_json(
        "/api/history",
        params={
            "symbol": ticker,
            "from": to_ts - _SUMMARY_BARS * 86400,
            "to": to_ts,
            "rs": "1D",
            "ajust": 1,
            "countback": _SUMMARY_BARS,
            "currencyCode": "RON",
        },
    )
    data = data or {}
    times = data.get("t") or []
    closes = [c for c in (data.get("c") or []) if isinstance(c, (int, float))]
    if not closes:
        return {"currency": "RON", "last_close": None}

    last = closes[-1]
    year = closes[-_YEAR_BARS:]

    def pct(old: float) -> float | None:
        return round((last / old - 1) * 100, 2) if old else None

    return {
        "currency": "RON",
        "last_close": last,
        "last_bar_date": datetime.fromtimestamp(int(times[-1]), tz=UTC).isoformat()
        if times
        else None,
        "bars": len(closes),
        "high_52w": max(year),
        "low_52w": min(year),
        "change_1y_pct": pct(closes[-_YEAR_BARS]) if len(closes) > _YEAR_BARS else None,
        "change_5y_pct": pct(closes[0]) if len(closes) > 1 else None,
    }


def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None:
    """Register the fundamentals tools (read-only) on *mcp*."""

    async def get_fundamentals(
        ticker: Annotated[
            str,
            Field(description='BVB ticker, e.g. "TLV", "SNP", or "ATB".'),
        ],
    ) -> dict[str, Any]:
        """Company details + valuation snapshot scraped from the detail page.

        Returns identity (ticker, name, isin, type, segment, category, status),
        the "Indicatori bursieri" valuation ratios (market_cap, per, pbv, eps,
        div_yield, dividend + dividend_year), issue info (shares_outstanding,
        nominal_value, share_capital, first_trade_date), and the ownership
        structure (shareholders: name/shares/percent). Amounts are in RON;
        indicators the page omits come back as null.

        Note: BVB does not expose multi-year income/balance/cash-flow statements
        as structured data, so there is no historical ROE/margin/FCF series here
        — pair this with get_candles (price history) for trend context.
        """
        return await _fundamentals(client, ticker)

    async def financial_summary(
        ticker: Annotated[
            str,
            Field(description='BVB ticker to summarise, e.g. "TLV" or "ATB".'),
        ],
    ) -> dict[str, Any]:
        """One-call bundle for a fundamental ("Buffett-style") analysis.

        Combines get_fundamentals with a price summary (last close, 52-week
        high/low, 1-year and ~5-year percent change) derived from daily history,
        so a caller has every input in a single call. It returns data, not a
        verdict — the analysis/judgement is left to the caller.

        Caveat (see ``note``): the inputs are a current valuation snapshot +
        dividend + ownership + price trend. BVB publishes no multi-year
        financial statements, so a full 10-year ROE/margin/FCF track record is
        not available from this source.
        """
        fundamentals = await _fundamentals(client, ticker)
        price = await _price_summary(client, ticker)
        return {
            "ticker": fundamentals.get("ticker") or ticker.upper(),
            "name": fundamentals.get("name"),
            "fundamentals": fundamentals,
            "price": price,
            "note": (
                "Snapshot valuation + dividend + ownership + price trend. BVB "
                "does not publish multi-year financial statements, so no "
                "historical ROE/margin/FCF series is available."
            ),
        }

    mcp.tool(get_fundamentals, annotations=_READ_ONLY)
    mcp.tool(financial_summary, annotations=_READ_ONLY)
