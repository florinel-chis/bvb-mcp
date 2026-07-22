"""HTML parsers for the BVB WebForms market-list and indices pages.

The datafeed's ``/api/search`` is server-capped (~30 results) and therefore not
a reliable universe source, so the full instrument list is scraped from the
server-rendered ``www.bvb.ro`` pages instead. These pages are plain ASP.NET
GridView tables; the parsers here use small, targeted regexes (no third-party
HTML dependency) tied to the exact markup those tables emit.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Rows of the market GridView (``<table id="gv">``): the first cell links to the
# instrument detail page (``?s=TICKER``) with the ticker in bold and the ISIN in
# a following ``<p>``; the second cell is the issuer name.
_GV_TABLE = re.compile(r'<table[^>]*\bid="gv"[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
_TICKER = re.compile(r"[?&]s=([^\"&]+)", re.IGNORECASE)
_BOLD = re.compile(r"<b[^>]*>(.*?)</b>", re.DOTALL | re.IGNORECASE)
_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
_TAG = re.compile(r"<[^>]+>")

# Indices overview page: the proprietary indices are listed in a single prose
# sentence, and each index that BVB renders a profile card for exposes its name
# in an ``<h2>`` and its ISIN in ``<span id="lblISIN">``.
_INDEX_TOKEN = re.compile(r"\b(BET(?:-[A-Z]+)*|BETPlus|BETAeRO|ROTX)\b")
_H2 = re.compile(r"<h2>\s*<b>(.*?)</b>\s*</h2>", re.DOTALL | re.IGNORECASE)
_LBL_ISIN = re.compile(r'<span[^>]*id="lblISIN"[^>]*>(.*?)</span>', re.DOTALL | re.IGNORECASE)


def _text(fragment: str) -> str:
    """Strip tags, unescape entities lightly, and collapse whitespace."""
    stripped = _TAG.sub(" ", fragment)
    stripped = stripped.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", stripped).strip()


def parse_market_rows(html: str) -> list[dict[str, Any]]:
    """Parse a ``/FinancialInstruments/Markets/*`` page into instrument rows.

    Returns one dict per row with ``ticker``, ``isin`` (12-char BVB ISIN, or
    None if the cell has none), and ``name`` (issuer). Rows without a resolvable
    ticker are skipped. Returns an empty list when the GridView is absent.
    """
    table = _GV_TABLE.search(html)
    if not table:
        return []
    rows: list[dict[str, Any]] = []
    for row_html in _ROW.findall(table.group(1)):
        cells = _CELL.findall(row_html)
        if len(cells) < 2:
            continue
        first = cells[0]
        ticker_match = _TICKER.search(first)
        bold = _BOLD.search(first)
        ticker = None
        if ticker_match:
            ticker = ticker_match.group(1).strip()
        elif bold:
            ticker = _text(bold.group(1)) or None
        if not ticker:
            continue
        isin_match = _ISIN.search(_text(first))
        rows.append(
            {
                "ticker": ticker,
                "isin": isin_match.group(1) if isin_match else None,
                "name": _text(cells[1]) or None,
            }
        )
    return rows


def parse_indices(html: str) -> list[dict[str, Any]]:
    """Parse the indices overview page into the BVB index universe.

    Returns one dict per index with ``symbol``, ``name``, and ``isin``. Every
    index's symbol is recovered, but ``name``/``isin`` are only populated for
    indices BVB renders a server-side profile card for (the rest load via
    client-side tabs); those come back as None.
    """
    # Symbols, in first-seen order, from anywhere on the page (the proprietary
    # list sentence plus ROTX). Dedupe while preserving order.
    seen: dict[str, None] = {}
    for token in _INDEX_TOKEN.findall(html):
        seen.setdefault(token, None)

    # name/isin for the profile cards that render server-side, keyed by the
    # leading symbol token of each <h2> (e.g. "BET® (BUCHAREST ...)" -> "BET").
    profiles: dict[str, dict[str, str | None]] = {}
    names = [_text(h) for h in _H2.findall(html)]
    isins = [_text(i) for i in _LBL_ISIN.findall(html)]
    for name, isin in zip(names, isins):
        head = unicodedata.normalize("NFKD", name)
        head = re.split(r"[\s(®]", head, maxsplit=1)[0].strip()
        if head:
            profiles[head] = {"name": name, "isin": isin or None}

    indices: list[dict[str, Any]] = []
    for symbol in seen:
        profile = profiles.get(symbol, {})
        indices.append(
            {
                "symbol": symbol,
                "name": profile.get("name"),
                "isin": profile.get("isin"),
            }
        )
    return indices


# --- Instrument detail page (fundamentals + company details) -----------------
#
# The detail page (FinancialInstrumentsDetails.aspx?s=TICKER) server-renders
# label/value tables: identity, "Indicatori bursieri" (valuation ratios), issue
# info, and an ownership table. Values are Romanian-formatted ("." groups
# thousands, "," is the decimal, a trailing " %" may appear); dates are
# dd.mm.yyyy. BVB publishes no multi-year statements here — this is a snapshot.

_COMPANY_NAME = re.compile(
    r'<h2 class="mBot0 large textStyled">\s*(.*?)\s*</h2>', re.DOTALL | re.IGNORECASE
)
_DIVIDEND = re.compile(
    r">Dividend\s*\((\d{4})\)\s*</td>\s*<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE
)
# A data row of the ownership table: name, shares, percent. The TOTAL row uses
# plain <td>s without class="text-right", so it does not match.
_SHAREHOLDER = re.compile(
    r'<td>([^<]+)</td>\s*<td class="text-right">([\d.]+)</td>'
    r'\s*<td class="text-right[^"]*">([\d.,]+)\s*%</td>',
    re.DOTALL | re.IGNORECASE,
)


def _detail_field(html: str, label: str) -> str:
    """Return the tag-stripped value cell following the label cell for *label*."""
    pattern = re.compile(
        r">" + re.escape(label) + r"\s*</td>\s*<td[^>]*>(.*?)</td>",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(html)
    return _text(match.group(1)) if match else ""


def _ro_float(value: str) -> float | None:
    """Parse a Romanian-formatted number; None if empty, '-', or unparseable."""
    value = value.strip().removesuffix("%").strip()
    if not value or value == "-":
        return None
    try:
        return float(value.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _ro_int(value: str) -> int | None:
    """Parse a Romanian-formatted integer ('.' groups thousands); None if empty."""
    value = value.strip().replace(".", "")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _iso_date(value: str) -> str | None:
    """Convert a dd.mm.yyyy date to ISO yyyy-mm-dd; None if it does not parse."""
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", value.strip())
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def parse_fundamentals(html: str) -> dict[str, Any] | None:
    """Parse the instrument detail page into a fundamentals dict.

    Returns None when the page carries no identity block (an unknown ticker).
    Numeric indicators absent from the page come back as None (not 0).
    """
    ticker = _detail_field(html, "Simbol:")
    name_match = _COMPANY_NAME.search(html)
    name = _text(name_match.group(1)) if name_match else ""
    if not ticker and not name:
        return None

    dividend = dividend_year = None
    div_match = _DIVIDEND.search(html)
    if div_match:
        dividend_year = int(div_match.group(1))
        dividend = _ro_float(_text(div_match.group(2)))

    shareholders: list[dict[str, Any]] = []
    for holder, shares, percent in _SHAREHOLDER.findall(html):
        holder = _text(holder)
        if not holder or holder.upper() == "TOTAL":
            continue
        shareholders.append(
            {"name": holder, "shares": _ro_int(shares), "percent": _ro_float(percent)}
        )

    return {
        "ticker": ticker or None,
        "name": name or None,
        "isin": _detail_field(html, "ISIN:") or None,
        "type": _detail_field(html, "Tip:") or None,
        "segment": _detail_field(html, "Segment:") or None,
        "category": _detail_field(html, "Categorie:") or None,
        "status": _detail_field(html, "Stare:") or None,
        "market_cap": _ro_float(_detail_field(html, "Capitalizare")),
        "per": _ro_float(_detail_field(html, "PER")),
        "pbv": _ro_float(_detail_field(html, "P/BV")),
        "eps": _ro_float(_detail_field(html, "EPS")),
        "div_yield": _ro_float(_detail_field(html, "DIVY")),
        "dividend": dividend,
        "dividend_year": dividend_year,
        "shares_outstanding": _ro_int(_detail_field(html, "Numar total actiuni")),
        "nominal_value": _ro_float(_detail_field(html, "Valoare Nominala")),
        "share_capital": _ro_float(_detail_field(html, "Capital social")),
        "first_trade_date": _iso_date(_detail_field(html, "Data start tranzactionare")),
        "shareholders": shareholders,
    }
