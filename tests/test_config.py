"""Settings.from_env: defaults and overrides (no required variables)."""

from __future__ import annotations

import pytest

from bvb_mcp.config import DATAFEED_URL, DEFAULT_LANG, DEFAULT_USER_AGENT, WEB_URL, Settings

_ENV_VARS = ("BVB_DATAFEED_URL", "BVB_WEB_URL", "BVB_MCP_USER_AGENT", "BVB_LANG")


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    settings = Settings.from_env()
    assert settings.datafeed_url == DATAFEED_URL
    assert settings.web_url == WEB_URL
    assert settings.user_agent == DEFAULT_USER_AGENT
    assert settings.lang == DEFAULT_LANG


def test_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("BVB_DATAFEED_URL", "https://feed.example/")
    monkeypatch.setenv("BVB_WEB_URL", "https://web.example/")
    monkeypatch.setenv("BVB_MCP_USER_AGENT", "custom-agent")
    monkeypatch.setenv("BVB_LANG", "en")
    settings = Settings.from_env()
    # Trailing slashes are stripped so paths concatenate cleanly.
    assert settings.datafeed_url == "https://feed.example"
    assert settings.web_url == "https://web.example"
    assert settings.user_agent == "custom-agent"
    assert settings.lang == "en"


def test_blank_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    for name in _ENV_VARS:
        monkeypatch.setenv(name, "   ")
    settings = Settings.from_env()
    assert settings.datafeed_url == DATAFEED_URL
    assert settings.web_url == WEB_URL
    assert settings.user_agent == DEFAULT_USER_AGENT
    assert settings.lang == DEFAULT_LANG
