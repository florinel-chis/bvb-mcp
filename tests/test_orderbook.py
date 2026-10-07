"""Order book domain tests: get_order_book, parse_order_book, parse_trading_tab_form.

The page is located by visible text (tab label, section heading, column headers,
caption) — never by element ids or ASP.NET control names, which the server
generates and may regenerate. The end-to-end test proves it by regenerating
them on every render.
"""

from __future__ import annotations

import secrets
from urllib.parse import parse_qs

import fastmcp
import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.parse import parse_order_book, parse_trading_tab_form
from bvb_mcp.tools import orderbook

WEB = "https://www.bvb.ro"
DETAIL = rf"{WEB}/FinancialInstruments/Details/FinancialInstrumentsDetails\.aspx.*"
# The Tranzactionare button's name as recorded in fixtures/detail-atb.html; the
# mocked site replaces it on every render.
FIXTURE_TAB_BUTTON = "ctl00$body$IFTC$07eeca91-ce47-42f3-a75b-a703b6dafb45"
HEADING = '<h2 class="styled">Order book piata principala (top 5)</h2>'


@respx.mock
async def test_get_order_book_with_regenerated_ids(make_server, settings, load_fixture) -> None:
    # Each GET renders the tab button under a new name (new naming-container
    # prefix + new GUID); each POST answers with the book table under a new id.
    issued: dict[str, str] = {}

    def render_get(request: httpx.Request) -> Response:
        issued["button"] = f"ctl{secrets.token_hex(1)}$main$TABS${secrets.token_hex(8)}"
        page = load_fixture("detail-atb.html").replace(FIXTURE_TAB_BUTTON, issued["button"])
        return Response(200, text=page)

    def render_post(request: httpx.Request) -> Response:
        page = load_fixture("detail-atb-trading.html")
        return Response(200, text=page.replace("gvMMOrderBook", "gv" + secrets.token_hex(8)))

    get = respx.get(url__regex=DETAIL).mock(side_effect=render_get)
    post = respx.post(url__regex=DETAIL).mock(side_effect=render_post)
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

    # The postback echoes the button name from the page it was served, plus
    # every named hidden field (incl. the empty __VIEWSTATEENCRYPTED).
    assert get.calls.last.request.url.params["s"] == "ATB"
    form = parse_qs(post.calls.last.request.content.decode(), keep_blank_values=True)
    assert form[issued["button"]] == ["Tranzactionare"]
    for field in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        assert form[field][0]
    assert form["__VIEWSTATEENCRYPTED"] == [""]
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


def test_parse_trading_tab_form() -> None:
    # Attribute order and case vary; the button's name is whatever the page
    # says; nameless inputs and other tabs' buttons are not sent; every named
    # hidden field is — like a browser submitting the clicked tab.
    html = """<form method="post" action="./x.aspx?s=ATB">
<input Value="Grafice" NAME="ctl00$x$other" type="submit" />
<input value='Tranzactionare' class="btn" name="zz$9f$TAB-abc" TYPE="SUBMIT">
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="a&amp;b" />
<input name="__VIEWSTATEENCRYPTED" type="hidden" value="" />
<input type="hidden" ID="hAdd2PO" Value="Adauga la PORTOFOLIU" />
<input type="text" id="autocomplete-form" placeholder="Nume" />
</form>"""
    assert parse_trading_tab_form(html) == {
        "zz$9f$TAB-abc": "Tranzactionare",
        "__VIEWSTATE": "a&b",
        "__VIEWSTATEENCRYPTED": "",
    }
    no_button = '<form><input type="hidden" name="__VIEWSTATE" value="x"></form>'
    assert parse_trading_tab_form(no_button) is None


def test_parse_order_book_partial() -> None:
    # Thin book: three bids, one ask; blank cells must not become levels. The
    # table has no id: it is found from the section heading.
    html = (
        HEADING
        + """<div><table class="table"><thead><tr><th>&nbsp;</th><th>Bid Vol</th><th>Bid</th>
<th>Ask</th><th>Ask Vol</th><th>&nbsp;</th></tr></thead><tbody>
<tr><td>x</td><td>1.200</td><td>10,5000</td><td>10,9000</td><td>300</td><td>x</td></tr>
<tr><td>x</td><td>50</td><td>10,4000</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><td>x</td><td>7</td><td>10,0000</td><td></td><td></td><td></td></tr>
</tbody></table></div>
<div class="caption">Ultima actualizare: 15.01.2026 10:31:07</div>"""
    )
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


def test_parse_order_book_columns_by_header() -> None:
    # Columns mapped by header text, not position: no depth bars, asks first.
    html = (
        HEADING + "<table><tr><th>ask</th><th>ASK VOL</th><th>Bid</th><th>Bid Vol</th></tr>"
        "<tr><td>2,0100</td><td>46.339</td><td>1,9960</td><td>3.845</td></tr></table>"
    )
    book = parse_order_book(html)
    assert book is not None
    assert book["bids"] == [{"price": 1.996, "volume": 3845}]
    assert book["asks"] == [{"price": 2.01, "volume": 46339}]


def test_parse_order_book_empty_and_missing() -> None:
    header_only = (
        HEADING + "<table><thead><tr><th>Bid Vol</th><th>Bid</th><th>Ask</th>"
        "<th>Ask Vol</th></tr></thead><tbody></tbody></table>"
    )
    assert parse_order_book(header_only) == {"bids": [], "asks": [], "updated_at": None}
    assert parse_order_book("<html>summary tab only</html>") is None


def test_parse_order_book_no_table_under_heading() -> None:
    # A zero-row ASP.NET GridView renders no <table>: the heading alone is an
    # empty book. The NEXT section's table and caption must not be used.
    html = (
        HEADING + "<div></div>"
        '<div class="caption">Ultima actualizare: 07.10.2026 18:00:00</div>'
        '<h2 class="styled">Ultimele tranzactii de astazi</h2>'
        "<table><tr><th>Bid Vol</th><th>Bid</th><th>Ask</th><th>Ask Vol</th></tr>"
        "<tr><td>9</td><td>9,0000</td><td>9,1000</td><td>9</td></tr></table>"
        '<div class="caption">Ultima actualizare: 01.01.2020 00:00:00</div>'
    )
    assert parse_order_book(html) == {
        "bids": [],
        "asks": [],
        "updated_at": "2026-10-07T18:00:00+03:00",
    }


def test_parse_order_book_unknown_columns() -> None:
    html = HEADING + "<table><tr><th>Pret</th><th>Volum</th></tr><tr><td>1,0</td><td>5</td></tr>"
    with pytest.raises(ValueError, match="layout changed"):
        parse_order_book(html + "</table>")


def test_parse_order_book_bad_timestamp() -> None:
    # Matches the caption pattern but is not a real date: no crash, just null.
    html = HEADING + '<div class="caption">Ultima actualizare: 32.13.2026 25:00:00</div>'
    book = parse_order_book(html)
    assert book is not None
    assert book["updated_at"] is None


def test_parse_order_book_empty_data_text() -> None:
    # A GridView with EmptyDataText renders one full-width message cell and no
    # column headers: that is an empty book, not a layout change.
    html = HEADING + '<table><tr><td colspan="6">Nu exista ordine</td></tr></table>'
    assert parse_order_book(html) == {"bids": [], "asks": [], "updated_at": None}


@respx.mock
async def test_get_order_book_unknown_columns(make_server, settings, load_fixture) -> None:
    # The postback answers with a book whose columns are no longer recognisable.
    respx.get(url__regex=DETAIL).mock(
        return_value=Response(200, text=load_fixture("detail-atb.html"))
    )
    respx.post(url__regex=DETAIL).mock(
        return_value=Response(
            200,
            text=HEADING + "<table><tr><th>Pret</th></tr><tr><td>1</td><td>2</td></tr></table>",
        )
    )
    server = make_server(settings, orderbook.register)
    async with fastmcp.Client(server) as c:
        with pytest.raises(ToolError, match="columns not found"):
            await c.call_tool("get_order_book", {"ticker": "ATB"})
