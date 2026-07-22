"""HTML parser tests, driven by the captured live fixtures."""

from __future__ import annotations

from bvb_mcp.parse import parse_indices, parse_market_rows


def test_parse_market_rows_from_shares_fixture(load_fixture) -> None:
    rows = parse_market_rows(load_fixture("shares.html"))
    assert len(rows) == 88
    # Every share row carries a 12-char ISIN.
    assert all(row["isin"] and len(row["isin"]) == 12 for row in rows)
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["TLV"] == {
        "ticker": "TLV",
        "isin": "ROTLVAACNOR1",
        "name": "BANCA TRANSILVANIA S.A.",
    }
    assert by_ticker["SNP"]["name"] == "OMV PETROM S.A."


def test_parse_market_rows_empty_when_no_table() -> None:
    assert parse_market_rows("<html><body>no grid here</body></html>") == []


def test_parse_indices_from_overview_fixture(load_fixture) -> None:
    indices = parse_indices(load_fixture("indices-overview.html"))
    symbols = [row["symbol"] for row in indices]
    # All 12 proprietary indices plus ROTX, in listing order, deduplicated.
    assert symbols == [
        "BET",
        "BET-FI",
        "BET-NG",
        "BET-XT",
        "BET-BK",
        "BETPlus",
        "BET-TR",
        "BET-XT-TR",
        "BET-TRN",
        "BET-XT-TRN",
        "BETAeRO",
        "BET-EF",
        "ROTX",
    ]
    bet = indices[0]
    assert bet["symbol"] == "BET"
    assert bet["isin"] == "ROXBSEI00005"
    assert "BUCHAREST EXCHANGE TRADING" in bet["name"]
    # Indices without a server-rendered profile card expose only their symbol.
    assert indices[-1] == {"symbol": "ROTX", "name": None, "isin": None}
