"""Domain tool modules.

Every module in this package follows one contract::

    def register(mcp: FastMCP, client: BvbClient, settings: Settings) -> None

- Tools are async closures over ``client``, defined inside ``register()``.
- Every tool is read-only (the BVB backend has no write surface) and is
  registered unconditionally via ``mcp.tool(fn, annotations={"readOnlyHint": True})``.
- Every tool has a docstring (it becomes the tool description) stating what it
  does and its parameters' units/formats/enums. List tools accept a ``limit``
  parameter and return trimmed JSON-serializable dicts/lists.
"""
