"""Environment-driven configuration.

The BVB backend is a public, read-only, unauthenticated service, so there are
no credentials to carry — every setting has a safe default and only exists so a
deployment (or the test suite) can override a host or the browser-like headers.
Nothing is read from files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DATAFEED_URL = "https://wapi.bvb.ro"
WEB_URL = "https://www.bvb.ro"

# A browser-like User-Agent and a bvb.ro Referer are sent defensively: the
# backend does not require them today, but they guard against a future WAF rule
# that rejects obvious non-browser clients. No cookies and no token are sent —
# the datafeed's X-SK-API token is not scraped (see the README's "Auth" note).
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_LANG = "ro"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the server.

    Attributes:
        datafeed_url: Base URL of the TradingView-UDF datafeed
            (``https://wapi.bvb.ro``).
        web_url: Base URL of the WebForms market-list site
            (``https://www.bvb.ro``), scraped for the instrument universe.
        user_agent: Browser-like ``User-Agent`` sent on every request.
        lang: Language passed to the datafeed ``/config`` endpoint (``ro``).
    """

    datafeed_url: str = DATAFEED_URL
    web_url: str = WEB_URL
    user_agent: str = DEFAULT_USER_AGENT
    lang: str = DEFAULT_LANG

    @classmethod
    def from_env(cls) -> Settings:
        """Build :class:`Settings` from the process environment.

        Variables (all optional):
            BVB_DATAFEED_URL: override the datafeed base URL.
            BVB_WEB_URL: override the market-list site base URL.
            BVB_MCP_USER_AGENT: override the browser-like User-Agent.
            BVB_LANG: language for the datafeed config (defaults to ``ro``).
        """
        datafeed_url = os.environ.get("BVB_DATAFEED_URL", "").strip() or DATAFEED_URL
        web_url = os.environ.get("BVB_WEB_URL", "").strip() or WEB_URL
        user_agent = os.environ.get("BVB_MCP_USER_AGENT", "").strip() or DEFAULT_USER_AGENT
        lang = os.environ.get("BVB_LANG", "").strip() or DEFAULT_LANG
        return cls(
            datafeed_url=datafeed_url.rstrip("/"),
            web_url=web_url.rstrip("/"),
            user_agent=user_agent,
            lang=lang,
        )
