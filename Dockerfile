# Build stage: resolve and install the locked dependency set into a venv.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/

# --no-editable installs a real wheel into the venv, so the runtime stage needs
# only /app/.venv and never the source tree.
RUN uv sync --frozen --no-dev --no-editable

# Runtime stage: slim image, non-root user, venv only.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="bvb-mcp" \
      org.opencontainers.image.description="Read-only MCP server for the Bucharest Stock Exchange (BVB) public backend" \
      org.opencontainers.image.source="https://github.com/florinel-chis/bvb-mcp" \
      org.opencontainers.image.licenses="MIT"

RUN useradd -r app

COPY --from=build /app/.venv /app/.venv

# PYTHONUNBUFFERED keeps the stdio transport responsive: under `docker run -i`
# stdout is a pipe (block-buffered by default), which can stall the JSON-RPC
# handshake until the buffer fills. Diagnostics go to stderr, so stdout stays a
# clean JSON-RPC channel.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

# HTTP transport (optional) listens here; harmless for the default stdio mode.
EXPOSE 8000

# stdio transport by default — MCP clients run `docker run -i --rm <image>`.
# Append `--transport http --host 0.0.0.0 --allow-remote --port 8000` to serve
# MCP over HTTP instead. The HTTP endpoint is unauthenticated, so publish the
# port on loopback only (`-p 127.0.0.1:8000:8000`) or front it with an
# authenticating proxy — see the Safety section of the README.
ENTRYPOINT ["bvb-mcp"]
