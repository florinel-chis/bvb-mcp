"""BvbClient: headers, JSON/text/HTML fetch, error mapping, 429 retry."""

from __future__ import annotations

import pytest
import respx
from fastmcp.exceptions import ToolError
from httpx import Response

from bvb_mcp.client import (
    DEFAULT_RETRY_AFTER,
    MAX_RETRY_AFTER,
    BvbClient,
    _retry_after_seconds,
)
from bvb_mcp.config import Settings

DATAFEED = "https://wapi.bvb.ro"
WEB = "https://www.bvb.ro"


@pytest.fixture
def client(settings: Settings) -> BvbClient:
    return BvbClient(settings)


@respx.mock
async def test_datafeed_json_sends_browser_headers(client: BvbClient) -> None:
    route = respx.get(f"{DATAFEED}/api/config").mock(
        return_value=Response(200, json={"supported_resolutions": ["1D"]})
    )
    data = await client.datafeed_json("/api/config", params={"lang": "ro"})
    assert data == {"supported_resolutions": ["1D"]}
    request = route.calls.last.request
    assert request.headers["User-Agent"].startswith("Mozilla/")
    assert request.headers["Referer"] == "https://www.bvb.ro/"
    assert request.url.params["lang"] == "ro"


@respx.mock
async def test_datafeed_text_returns_body(client: BvbClient) -> None:
    respx.get(f"{DATAFEED}/api/time").mock(return_value=Response(200, text="1784729782"))
    assert (await client.datafeed_text("/api/time")).strip() == "1784729782"


@respx.mock
async def test_web_html_uses_web_host(client: BvbClient) -> None:
    route = respx.get(f"{WEB}/FinancialInstruments/Markets/Shares").mock(
        return_value=Response(200, text="<html>ok</html>")
    )
    html = await client.web_html("/FinancialInstruments/Markets/Shares")
    assert html == "<html>ok</html>"
    assert route.calls.last.request.headers["User-Agent"].startswith("Mozilla/")


@respx.mock
async def test_none_params_are_stripped(client: BvbClient) -> None:
    route = respx.get(f"{DATAFEED}/api/history").mock(return_value=Response(200, json={"s": "ok"}))
    await client.datafeed_json("/api/history", params={"symbol": "TLV", "countback": None})
    url = route.calls.last.request.url
    assert url.params["symbol"] == "TLV"
    assert "countback" not in url.params


@respx.mock
async def test_error_maps_to_tool_error_with_backend_message(client: BvbClient) -> None:
    respx.get(f"{DATAFEED}/api/history").mock(
        return_value=Response(401, json={"Message": "Authorization has been denied for this request."})
    )
    with pytest.raises(ToolError, match="HTTP 401: Authorization has been denied"):
        await client.datafeed_json("/api/history")


@respx.mock
async def test_error_without_json_uses_reason_phrase(client: BvbClient) -> None:
    respx.get(f"{DATAFEED}/api/history").mock(return_value=Response(500, text=""))
    with pytest.raises(ToolError, match="HTTP 500"):
        await client.datafeed_json("/api/history")


@respx.mock
async def test_invalid_json_raises_tool_error(client: BvbClient) -> None:
    respx.get(f"{DATAFEED}/api/config").mock(return_value=Response(200, text="not json"))
    with pytest.raises(ToolError, match="invalid JSON"):
        await client.datafeed_json("/api/config")


@respx.mock
async def test_429_retries_once_honouring_retry_after(client: BvbClient) -> None:
    route = respx.get(f"{DATAFEED}/api/time").mock(
        side_effect=[
            Response(429, headers={"Retry-After": "0"}),
            Response(200, text="1"),
        ]
    )
    assert (await client.datafeed_text("/api/time")) == "1"
    assert route.call_count == 2


@respx.mock
async def test_second_429_raises(client: BvbClient) -> None:
    route = respx.get(f"{DATAFEED}/api/time").mock(
        return_value=Response(429, headers={"Retry-After": "0"})
    )
    with pytest.raises(ToolError, match="HTTP 429"):
        await client.datafeed_text("/api/time")
    assert route.call_count == 2


def test_retry_after_defaults_and_caps() -> None:
    assert _retry_after_seconds(Response(429)) == DEFAULT_RETRY_AFTER
    assert _retry_after_seconds(Response(429, headers={"Retry-After": "later"})) == DEFAULT_RETRY_AFTER
    assert _retry_after_seconds(Response(429, headers={"Retry-After": "-1"})) == DEFAULT_RETRY_AFTER
    assert _retry_after_seconds(Response(429, headers={"Retry-After": "0.5"})) == 0.5
    assert _retry_after_seconds(Response(429, headers={"Retry-After": "86400"})) == MAX_RETRY_AFTER


def test_retry_after_rejects_non_finite_values() -> None:
    for raw in ("inf", "Infinity", "nan", "1e309"):
        assert _retry_after_seconds(Response(429, headers={"Retry-After": raw})) == DEFAULT_RETRY_AFTER
