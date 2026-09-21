# kev-mcp

The approved contracts are `docs/b-implementation_plans/IP-001-kev-mcp.md` and
`docs/b-implementation_plans/IP-002-durable-services.md`.
Keep the MCP bridge free of GPU dependencies. The runtime imports pinned upstream Kev.
Do not commit document databases, credentials, private hostnames or weights.

Before publishing code, run:

```sh
uv run ruff check .
uv run mypy src/kev_mcp
uv run pytest -q
uv build
```

Real GPU acceptance uses `scripts/acceptance.py`. Record revisions and distinguish
token preflight from inference and answer quality. A fake backend does not establish
GPU or application-client compatibility.

## Evolution Log

- 2026-09-21 — IP-002: Added durable dual-model systemd templates, authenticated
  MCP readiness and shared-store restart acceptance. See docs/durable-services.md.

- 2026-09-21 — IP-001: Added the document MCP bridge and a separate guarded upstream
  Kev runtime. Native TypeSafe SDK evaluation; SQLite store per instance; stdio and
  authenticated Streamable HTTP. ROCm acceptance passed on 0.8B and 4B. See CR-001.
