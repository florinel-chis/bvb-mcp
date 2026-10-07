"""Candle tool: OHLCV history — the workhorse of this server.

Reads the datafeed ``/api/history`` endpoint, which is a customised TradingView
UDF feed with two quirks this module encapsulates:

- Daily resolution is ``rs=1D``, not the bare ``D`` the config advertises (bare
  ``D`` returns HTTP 500). :data:`_RESOLUTIONS` centralises the mapping.
- ``ajust``, ``countback``, and ``currencyCode`` are all required on every
  request; this module always supplies them, deriving ``countback`` from the
  requested window when the caller does not pass one.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings

# Friendly resolution -> the exact ``rs`` value the history endpoint accepts.
# Minute resolutions are numeric; "D"/"W"/"M" (and their "1x" spellings) map to
# the daily/weekly/monthly codes. Bare "D" is deliberately absent from the
# output values — the endpoint rejects it.
_RESOLUTIONS: dict[str, str] = {
    "1": "1",
    "5": "5",
    "15": "15",
    "30": "30",
    "60": "60",
    "1D": "1D",
    "D": "1D",
    "1W": "1W",
    "W": "1W",
    "1M": "1M",
    "M": "1M",
}

# Approximate seconds per bar, used only to size ``countback`` from a window.
_BAR_SECONDS: dict[str, int] = {
    "1": 60,
    "5": 300,
    "15": 900,
    "30": 1800,
    "60": 3600,
    "1D": 86_400,
    "1W": 604_800,
    "1M": 2_629_800,
}

_DEFAULT_COUNTBACK = 300
_MAX_COUNTBACK = 5000

_READ_ONLY = {"readOnlyHint": True}


def _resolve(resolution: str) -> str:
    """Map a friendly resolution to the history ``rs`` value, or raise."""
    key = resolution.strip().upper()
    rs = _RESOLUTIONS.get(key)
    if rs is None:
        supported = "1, 5, 15, 30, 60, 1D, 1W, 1M"
        raise ToolError(f"unsupported resolution {resolution!r}; supported: {supported}")
    return rs


def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None:
    """Register the candle tool (read-only) on *mcp*."""

    async def get_candles(
        ticker: Annotated[
            str,
            Field(description='BVB ticker, e.g. "TLV", "SNP", or an index like "BET".'),
        ],
        resolution: Annotated[
            str,
            Field(
                description=(
                    "Bar size (case-insensitive). Minutes: 1, 5, 15, 30, 60. "
                    "Daily: 1D (or D). Weekly: 1W. Monthly: 1M."
                )
            ),
        ] = "1D",
        from_: Annotated[
            int | None,
            Field(description="Window start, unix seconds (UTC). Derived from countback if omitted."),
        ] = None,
        to: Annotated[
            int | None,
            Field(description="Window end, unix seconds (UTC). Defaults to now."),
        ] = None,
        countback: Annotated[
            int | None,
            Field(
                description=(
                    "Number of bars ending at 'to'. Overrides the from/to span "
                    "when set; derived from the span (or defaults to 300) otherwise."
                ),
                ge=1,
            ),
        ] = None,
        adjusted: Annotated[
            bool,
            Field(description="Split/dividend-adjusted prices (True) or raw (False)."),
        ] = True,
        currency: Annotated[
            str,
            Field(description="Quote currency code, e.g. 'RON'."),
        ] = "RON",
    ) -> list:
        """Fetch OHLCV candles for a BVB ticker.

        Returns bars oldest-first, each ``{time, open, high, low, close,
        volume}`` where ``time`` is an ISO 8601 UTC timestamp and ``volume`` is
        an integer (null for indices such as BET, which carry no volume). An empty list means the datafeed had no data for the window
        (not an error).

        The window is resolved as: ``to`` defaults to now; ``countback`` (when
        given) fixes the number of bars, otherwise it is derived from the
        ``from_``/``to`` span (capped at 5000) or defaults to 300; ``from_``
        defaults to ``to`` minus ``countback`` bars. Daily bars reach back to
        the 1990s; intraday resolutions only cover a recent window.
        """
        rs = _resolve(resolution)
        bar_seconds = _BAR_SECONDS[rs]

        to_ts = to if to is not None else int(time.time())
        if countback is not None:
            count = countback
        elif from_ is not None:
            count = min(_MAX_COUNTBACK, max(1, math.ceil((to_ts - from_) / bar_seconds)))
        else:
            count = _DEFAULT_COUNTBACK
        from_ts = from_ if from_ is not None else to_ts - count * bar_seconds

        data = await client.datafeed_json(
            "/api/history",
            params={
                "symbol": ticker,
                "from": from_ts,
                "to": to_ts,
                "rs": rs,
                "ajust": 1 if adjusted else 0,
                "countback": count,
                "currencyCode": currency,
            },
        )
        data = data or {}
        status = data.get("s")
        if status == "no_data":
            return []
        if status != "ok":
            raise ToolError(f"history unavailable for {ticker}: {status or 'unknown status'}")

        times = data.get("t") or []
        opens = data.get("o") or []
        highs = data.get("h") or []
        lows = data.get("l") or []
        closes = data.get("c") or []
        volumes = data.get("v") or []
        bars: list[dict[str, Any]] = []
        for i, ts in enumerate(times):
            bars.append(
                {
                    "time": datetime.fromtimestamp(int(ts), tz=UTC).isoformat(),
                    "open": opens[i] if i < len(opens) else None,
                    "high": highs[i] if i < len(highs) else None,
                    "low": lows[i] if i < len(lows) else None,
                    "close": closes[i] if i < len(closes) else None,
                    # Indices carry no volume: the datafeed sends null per bar.
                    "volume": int(volumes[i])
                    if i < len(volumes) and volumes[i] is not None
                    else None,
                }
            )
        return bars

    mcp.tool(get_candles, annotations=_READ_ONLY)
