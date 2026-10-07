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
from importlib import metadata, resources

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse

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


def build_server(settings: Settings, *, ui: bool = True) -> FastMCP:
    """Create the FastMCP server with every domain's tools registered.

    Instantiates one shared :class:`BvbClient` and passes it to each domain
    module's ``register(mcp, client, settings)``. All tools are read-only.

    With *ui* (the default), the HTTP transport also serves the playground page
    at ``/``: a self-contained MCP client that talks to this server's ``/mcp``
    endpoint from the browser, so it adds no capability beyond ``/mcp`` itself.
    """
    mcp = FastMCP("bvb-mcp", version=metadata.version("bvb-mcp"))
    client = BvbClient(settings)
    for name in DOMAIN_MODULES:
        module = importlib.import_module(f"bvb_mcp.tools.{name}")
        module.register(mcp, client, settings)
    if ui:
        page = (resources.files("bvb_mcp") / "web" / "index.html").read_text(encoding="utf-8")

        @mcp.custom_route("/", methods=["GET"])
        async def playground(request: Request) -> HTMLResponse:
            return HTMLResponse(page)

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
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="HTTP transport: serve only the MCP endpoint, not the playground page at /",
    )
    args = parser.parse_args()

    # The HTTP transport is unauthenticated: anyone who can reach the port can
    # call every tool. A non-loopback bind must be an explicit, flagged choice.
    if args.transport == "http" and not args.allow_remote and not _is_loopback_host(args.host):
        parser.error(
            f"refusing to bind the unauthenticated HTTP transport to non-loopback host "
            f"{args.host!r}; pass --allow-remote if the network really is trusted"
        )

    mcp = build_server(Settings.from_env(), ui=not args.no_ui)
    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
