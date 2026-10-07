"""Server assembly and console entry point.

Domain tool modules live under ``bvb_mcp.tools``, one per API domain, each
exposing ``register(mcp, client, settings)``:

- ``diagnostics`` — datafeed server time and configuration
- ``symbols`` — symbol metadata and datafeed search
- ``candles`` — OHLCV history (the workhorse)
- ``universe`` — the full instrument list and the index universe

``DOMAIN_MODULES`` lists the modules :func:`build_server` wires in. A listed
module that is missing or lacks ``register`` makes :func:`build_server` raise
immediately. Every tool is read-only — the BVB backend has no write surface —
so there is no trading gate.
"""

from __future__ import annotations

import argparse
import importlib
import ipaddress

from fastmcp import FastMCP

from bvb_mcp.client import BvbClient
from bvb_mcp.config import Settings

DOMAIN_MODULES: tuple[str, ...] = (
    "diagnostics",
    "symbols",
    "candles",
    "universe",
    "fundamentals",
    "orderbook",
)


def build_server(settings: Settings) -> FastMCP:
    """Create the FastMCP server with every domain's tools registered.

    Instantiates one shared :class:`BvbClient` and passes it to each domain
    module's ``register(mcp, client, settings)``. All tools are read-only.
    """
    mcp = FastMCP("bvb-mcp")
    client = BvbClient(settings)
    for name in DOMAIN_MODULES:
        module = importlib.import_module(f"bvb_mcp.tools.{name}")
        module.register(mcp, client, settings)
    return mcp


def _is_loopback_host(host: str) -> bool:
    """True when host is a loopback name or address (a safe local-only bind)."""
    candidate = host.strip()
    if candidate.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def main() -> None:
    """Console entry point."""
    parser = argparse.ArgumentParser(
        prog="bvb-mcp",
        description="MCP server for the Bucharest Stock Exchange (BVB) public backend",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "allow --host to be a non-loopback address; the HTTP transport has "
            "no authentication of its own, so only combine this with an "
            "authenticating reverse proxy or an otherwise-restricted network"
        ),
    )
    args = parser.parse_args()

    # The HTTP transport is unauthenticated: anyone who can reach the port can
    # call every tool. A non-loopback bind must be an explicit, flagged choice.
    if args.transport == "http" and not args.allow_remote and not _is_loopback_host(args.host):
        parser.error(
            f"refusing to bind the unauthenticated HTTP transport to non-loopback host "
            f"{args.host!r}; pass --allow-remote if the network really is trusted"
        )

    mcp = build_server(Settings.from_env())
    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
