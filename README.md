# bvb-mcp

Read-only MCP server for the **Bucharest Stock Exchange** (Bursa de Valori
București, BVB). It exposes BVB's own public backend — the TradingView-UDF
datafeed at `wapi.bvb.ro` and the market-list pages at `www.bvb.ro` — as MCP
tools: instrument universe, symbol search and metadata, OHLCV candles,
fundamentals, and the top-5 order book.

No account, no API key, no token: the BVB backend is public and unauthenticated.
Every tool is read-only; there is nothing to trade through here.

## Features

- OHLCV candles for any BVB ticker or index (`get_candles`), with a clean
  `resolution` parameter that hides the datafeed's `1D`-not-`D` quirk.
- Full instrument universe scraped from the exchange's market-list pages
  (`list_instruments`) — ticker + ISIN + name — plus the index universe
  (`list_indices`).
- Datafeed symbol search (`search_symbol`) and per-symbol metadata
  (`get_symbol_info`), with diagnostics (`server_time`, `datafeed_config`).
- Browser-like `User-Agent` and `Referer: https://www.bvb.ro/` on every request
  (defensive; no cookies, no token).
- One automatic retry on HTTP 429, honouring `Retry-After` (capped at 30s).
- stdio transport by default, HTTP (`/mcp`) on request.

## Tools

All tools are read-only (there are no write tools):

| Tool | Description |
|---|---|
| `list_instruments` | List a market's instrument universe (ticker + ISIN + name) by scraping the BVB market-list page. Markets: `shares`, `bonds`, `fund-units` (ETFs), `warrants`, `certificates` (`structured`) |
| `list_indices` | List the BVB index universe (BET, BET-TR, BET-FI, ROTX, …) |
| `search_symbol` | Datafeed symbol search by ticker/name (server-capped at ~30 results) |
| `get_symbol_info` | Resolve a ticker to its metadata: name, type, session, timezone, currency, sector/industry |
| `get_candles` | OHLCV candles for a ticker/index at minute/daily/weekly/monthly resolution |
| `get_fundamentals` | Company details + valuation snapshot scraped from the detail page: identity, Indicatori bursieri (market cap, P/E, P/BV, EPS, div yield, dividend), issue info, and ownership structure |
| `financial_summary` | One-call bundle for a fundamental ("Buffett-style") analysis: `get_fundamentals` + a price summary (last close, 52-week range, 1y/5y change). Returns data, not a verdict |
| `get_order_book` | Main-market (REGS) top-5 order book: bids/asks as `{price, volume}` levels, `updated_at`, and a `delayed` flag (BVB publishes it 15 min delayed). Replays the detail page's "Tranzactionare" tab postback (two requests) |
| `server_time` | Datafeed server time (reachability check) |
| `datafeed_config` | Datafeed configuration: instrument-type codes and supported resolutions |

### Notes on the data surface

- **Search is capped.** `search_symbol` mirrors the datafeed's own search,
  which returns roughly 30 results for broad queries. Use `list_instruments`
  (or `list_indices`) to enumerate the full universe.
- **The `1D` quirk.** The datafeed advertises a bare `D` for daily bars but the
  history endpoint only accepts `1D` (bare `D` returns HTTP 500). `get_candles`
  takes a friendly `resolution` (`1`, `5`, `15`, `30`, `60`, `1D`, `1W`, `1M`;
  `D`/`W`/`M` are accepted too) and sends the correct code.
- **Index metadata is partial.** `list_indices` always returns every index's
  `symbol`, but `name`/`isin` are populated only for the indices BVB renders a
  server-side profile card for; the rest load via client-side tabs and come
  back as `null`.
- **Rights / structured.** BVB publishes no standalone "rights" market page, and
  "structured products" (datafeed type `T`) are split across the `warrants` and
  `certificates` pages — `structured` is accepted as an alias for
  `certificates`.
- **No multi-year statements.** `get_fundamentals` / `financial_summary` expose
  BVB's current snapshot (valuation ratios, dividend, ownership) — BVB does not
  publish structured multi-year income/balance/cash-flow statements, so a full
  10-year ROE/margin/FCF track record is not available. Pair with `get_candles`
  for the price trend; the client (LLM) does the analysis.

## Configuration

All configuration is via environment variables, and all of it is optional — the
BVB backend needs no credentials.

| Variable | Default | Purpose |
|---|---|---|
| `BVB_DATAFEED_URL` | `https://wapi.bvb.ro` | Datafeed base URL |
| `BVB_WEB_URL` | `https://www.bvb.ro` | Market-list site base URL |
| `BVB_MCP_USER_AGENT` | a Chrome-like UA | `User-Agent` sent on every request |
| `BVB_LANG` | `ro` | Language for the datafeed config endpoint |

## Getting started

Run straight from the repository with [uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/florinel-chis/bvb-mcp bvb-mcp
```

The server speaks stdio by default; add `--transport http --port 8000` to serve
MCP over HTTP at `/mcp` instead. HTTP binds `127.0.0.1` by default, and a
non-loopback `--host` is refused unless `--allow-remote` is also passed — read
the [Safety](#safety) section before using that flag.

## MCP client configuration

Add the server to your MCP client's configuration (stdio, via `uvx`):

```json
{
  "mcpServers": {
    "bvb": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/florinel-chis/bvb-mcp", "bvb-mcp"]
    }
  }
}
```

Or run the Docker image (build it first, see below):

```json
{
  "mcpServers": {
    "bvb": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "bvb-mcp"]
    }
  }
}
```

## Docker

A small (~200 MB) multi-stage image that works both ways an MCP client might use
it — spawned per call over **stdio**, or as a long-running **HTTP** server. Both
paths are verified against BVB's live backend. The container only needs outbound
network to reach `wapi.bvb.ro` / `www.bvb.ro`; no credentials or volumes.

**Build:**

```bash
docker build -t bvb-mcp .
```

**stdio** — what an MCP client spawns (use `bvb-mcp` as the image name in the
docker config above):

```bash
docker run -i --rm bvb-mcp
```

**HTTP** — a shared, long-running server at `http://127.0.0.1:8000/mcp/`:

```bash
docker run --rm -p 127.0.0.1:8000:8000 bvb-mcp \
  --transport http --host 0.0.0.0 --port 8000 --allow-remote
```

`--host 0.0.0.0` binds inside the container so the port mapping works — which is
why `--allow-remote` is needed; the `127.0.0.1:` prefix on `-p` keeps the
endpoint reachable from this machine only (it is unauthenticated — see Safety).
If host port 8000 is taken, map another, e.g. `-p 127.0.0.1:8010:8000`.

**Share without a registry** — hand the image to someone as a file they
`docker load`, no Docker Hub / GHCR needed:

```bash
docker save bvb-mcp:latest | gzip > bvb-mcp.tar.gz   # you: export
docker load < bvb-mcp.tar.gz                          # them: image is now local
```

## Safety

- The HTTP transport has **no authentication**: anyone who can reach the `/mcp`
  endpoint can call every tool. Keep it bound to `127.0.0.1` (the CLI default;
  with Docker, publish as `-p 127.0.0.1:8000:8000`) or put it behind an
  authenticating reverse proxy. Never expose it directly on a public network.
- All tools are read-only — this server cannot place orders or move money.
- Use at your own risk. Nothing here is investment advice.

## Data & terms

This server ships **code, not data**. It fetches from BVB's own public backend
at request time and returns whatever BVB serves. Redistributing or otherwise
using BVB price data is subject to BVB's terms and any applicable market-data
licensing, and is **your responsibility** as the operator — the software makes
no representation about your right to store, redistribute, or trade on the data
it relays.

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
```

Tests are fully offline: HTTP is stubbed with `respx` against captured BVB
response fixtures in `tests/fixtures/`.

## License

MIT
