# Client connections

Automated tests use the official MCP Python client against real stdio and HTTP transports. These application examples are configuration guidance; they do not claim each named application was tested interactively.

The durable deployment additionally verified both HTTP endpoints through the installed
Hermes native MCP client in all 14 configured profiles, including real evaluations.
See [dual-model service setup](durable-services.md) for the tested Hermes configuration.
This does not claim Open WebUI testing or autonomous model tool-selection coverage.

## Coding agents and Hermes

For clients accepting `mcpServers` JSON, configure:

```json
{
  "mcpServers": {
    "kev": {
      "command": "uv",
      "args": ["--directory", "/path/to/kev-mcp", "run", "--locked", "kev-mcp"],
      "env": {
        "KEV_BASE_URL": "http://127.0.0.1:8009",
        "KEV_MCP_DB": "/path/to/private/kev.sqlite3"
      }
    }
  }
}
```

For Hermes, register a stdio MCP server with those command, arguments and environment values using the installed version's MCP configuration. For Codex, the equivalent TOML entry is `[mcp_servers.kev]`. Keep credentials in the client's secret storage. A remote agent must run the bridge there or use its HTTP URL: `localhost` means the client's own host.

Hermes's [current MCP configuration reference](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/mcp-config-reference.md) uses this YAML shape:

```yaml
mcp_servers:
  kev:
    command: uv
    args: ["--directory", "/path/to/kev-mcp", "run", "--locked", "kev-mcp"]
    env:
      KEV_BASE_URL: http://127.0.0.1:8009
      KEV_MCP_DB: /path/to/private/kev.sqlite3
    timeout: 180
    supports_parallel_tool_calls: false
```

The tool workflow is:

```text
kev_fetch_document(url) → document_id
kev_evaluate_document(document_id, questions) → answers + source + coverage
kev_evaluate_document(document_id, new_questions) → follow-up answers
```

An existing fetch/extract tool can submit text through `kev_store_document`. Prefer direct tool-to-tool transfer where the agent supports it; otherwise that initial text still passes through the caller before storage. Kev returns classifications and probabilities. It does not generate free-form explanations or source quotations.

## Open WebUI

Use a version with native Streamable HTTP MCP support. Register the bridge's `/mcp` URL as an MCP tool server and configure its bearer token. Enable the tools for a model with tool calling. Each service instance is a shared document workspace for its authenticated callers, not an isolated store per Open WebUI user.

In the [current Open WebUI interface](https://docs.openwebui.com/features/extensibility/mcp/), an administrator uses **Settings → Admin → Integrations → External Tool Servers → Add Connection**, selects **MCP (Streamable HTTP)**, enters the URL, and chooses **Bearer** with the configured token in the Key field. Native MCP support starts at v0.6.31. A container must use a reachable host address rather than its own loopback.

Uploads and Knowledge entries do not automatically appear in this store. Submit extracted text with `kev_store_document` or fetch a page with `kev_fetch_document`. No Knowledge-ID resolver is implemented.

For a proxy or wildcard binding, configure exact external Host values in `KEV_MCP_ALLOWED_HOSTS` and browser origins in `KEV_MCP_ALLOWED_ORIGINS`. Authentication is required off loopback; use a private network or TLS. No wildcard origins are accepted.

## Interpretation

Partial results cover only the selected lines. They cannot establish that a fact is absent from the full document. Oversized inputs must be reduced explicitly; combining chunk decisions is not automatically a valid whole-document conclusion. Test representative decisions before selecting a probability threshold.
