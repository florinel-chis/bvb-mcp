"""Order book domain tests: get_order_book and parse_order_book."""

from __future__ import annotations

from urllib.parse import parse_qs

import fastmcp
import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.parse import parse_order_book
from bvb_mcp.tools import orderbook

WEB = "https://www.bvb.ro"
DETAIL = rf"{WEB}/FinancialInstruments/Details/FinancialInstrumentsDetails\.aspx.*"
# The tab button's GUID changes on every render; the tool must echo the one
# from the page it was served (fixtures/detail-atb.html).
TAB_BUTTON = "ctl00$body$IFTC$07eeca91-ce47-42f3-a75b-a703b6dafb45"


@respx.mock
async def test_get_order_book(make_server, settings, load_fixture) -> None:
    get = respx.get(url__regex=DETAIL).mock(
        return_value=Response(200, text=load_fixture("detail-atb.html"))
    )
    post = respx.post(url__regex=DETAIL).mock(
        return_value=Response(200, text=load_fixture("detail-atb-trading.html"))
    )
    server = make_server(settings, orderbook.register)
    async with fastmcp.Client(server) as c:
        result = await c.call_tool("get_order_book", {"ticker": "ATB"})
    d = result.data

    assert d["ticker"] == "ATB"
    assert d["market"] == "REGS"
    assert d["currency"] == "RON"
    assert d["delayed"] is True
    assert d["updated_at"] == "2026-10-07T18:00:00+03:00"
    assert d["bids"][0] == {"price": 1.996, "volume": 3845}
    assert d["asks"][0] == {"price": 1.998, "volume": 6283}
    assert [lvl["price"] for lvl in d["bids"]] == [1.996, 1.97, 1.966, 1.964, 1.962]
    assert [lvl["volume"] for lvl in d["asks"]] == [6283, 11727, 46339, 1500, 2200]

    # The postback carries the page's form state and the trading tab button.
    assert get.calls.last.request.url.params["s"] == "ATB"
    form = parse_qs(post.calls.last.request.content.decode())
    assert form[TAB_BUTTON] == ["Tranzactionare"]
    for field in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        assert form[field][0]
    assert post.calls.last.request.headers["User-Agent"]
    assert post.calls.last.request.headers["Referer"] == f"{WEB}/"


@respx.mock
async def test_get_order_book_unknown_ticker(make_server, settings) -> None:
    respx.get(url__regex=DETAIL).mock(
        return_value=Response(200, text='<html><form id="aspnetForm"></form></html>')
    )
    server = make_server(settings, orderbook.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="no such BVB symbol"):
            await c.call_tool("get_order_book", {"ticker": "NOPE"})


@respx.mock
async def test_get_order_book_layout_changed(make_server, settings) -> None:
    # Known instrument, but the trading tab button is gone: fail loudly.
    respx.get(url__regex=DETAIL).mock(
        return_value=Response(
            200,
            text='<h2 class="mBot0 large textStyled">ANTIBIOTICE S.A.</h2>'
            '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="x" />',
        )
    )
    server = make_server(settings, orderbook.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="layout changed"):
            await c.call_tool("get_order_book", {"ticker": "ATB"})


def test_parse_order_book_partial() -> None:
    # Thin book: three bids, one ask; blank cells must not become levels.
    html = """<table id="gvMMOrderBook"><thead><tr><th>&nbsp;</th><th>Bid Vol</th></tr></thead>
<tbody>
<tr><td>x</td><td>1.200</td><td>10,5000</td><td>10,9000</td><td>300</td><td>x</td></tr>
<tr><td>x</td><td>50</td><td>10,4000</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><td>x</td><td>7</td><td>10,0000</td><td></td><td></td><td></td></tr>
</tbody></table>
<div class="caption">Ultima actualizare: 15.01.2026 10:31:07</div>"""
    book = parse_order_book(html)
    assert book is not None
    assert book["bids"] == [
        {"price": 10.5, "volume": 1200},
        {"price": 10.4, "volume": 50},
        {"price": 10.0, "volume": 7},
    ]
    assert book["asks"] == [{"price": 10.9, "volume": 300}]
    # January → EET (+02:00): Bucharest DST, not a fixed offset.
    assert book["updated_at"] == "2026-01-15T10:31:07+02:00"


def test_parse_order_book_empty_and_missing() -> None:
    empty = parse_order_book('<table id="gvMMOrderBook"><tbody></tbody></table>')
    assert empty == {"bids": [], "asks": [], "updated_at": None}
    assert parse_order_book("<html>summary tab only</html>") is None


def test_parse_order_book_bad_timestamp() -> None:
    # Matches the caption pattern but is not a real date: no crash, just null.
    html = (
        '<table id="gvMMOrderBook"><tbody></tbody></table>'
        '<div class="caption">Ultima actualizare: 32.13.2026 25:00:00</div>'
    )
    book = parse_order_book(html)
    assert book is not None
    assert book["updated_at"] is None


def test_parse_order_book_heading_without_table() -> None:
    # A zero-row ASP.NET GridView renders no <table>: heading alone = empty book.
    html = (
        '<h2 class="styled">Order book piata principala (top 5)</h2><div></div>'
        '<div class="caption">Ultima actualizare: 07.10.2026 18:00:00</div>'
    )
    assert parse_order_book(html) == {
        "bids": [],
        "asks": [],
        "updated_at": "2026-10-07T18:00:00+03:00",
    }
