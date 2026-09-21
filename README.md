# kev-mcp

A local MCP interface for asking typed questions about documents with [Kev](https://github.com/jaredpalmer/kev).

Fetch a page or submit extracted text, retain its document ID, then ask yes/no, multiple-choice or ordered-rating questions. Follow-up calls reuse the ID. The caller receives probabilities without carrying the full document in its own context.

The intended workflow is:

```text
Hermes / coding agent / Open WebUI
        │ MCP
        ▼
fetch or store document → document ID → typed questions
        │ official TypeSafe SDK
        ▼
local Kev System One API → decisions and probabilities
```

Kev supports yes/no, multiple-choice and ordered-rating questions. The calling agent handles explanations and synthesis. Documents remain in the tool's store so callers can ask follow-up questions by ID without carrying the full text in their own context.

## Project records

- [Implementation plan and acceptance criteria](docs/b-implementation_plans/IP-001-kev-mcp.md)
- [Native TypeSafe integration findings](docs/f-reports_reviews/2026-09-21-typesafe-integration.md)
- [Measured Kev 0.8B and 4B ROCm results](docs/f-reports_reviews/2026-09-21-rocm-baseline.md)
- [CR-001: completed implementation and end-to-end acceptance](docs/c-completion_reports/CR-001-kev-mcp.md)
- [Durable dual-model services and Hermes setup](docs/durable-services.md)
- [CR-002: service recovery and dual-model acceptance](docs/c-completion_reports/CR-002-durable-services.md)

Upstream Kev supplies model loading, tokenization, System One conversion and probability calculation. This project adds document handling, strict input checks and MCP access. It uses the official TypeSafe SDK, not the general-LLM System One Adapter. There is no cloud fallback.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). The bridge does not install PyTorch or model weights.

```sh
git clone https://github.com/abliter8-ai/kev-mcp.git
cd kev-mcp
uv sync --locked
uv run kev-mcp
```

Stdio is the default. Storage works immediately. Evaluation requires the [strict Kev runtime](docs/runtime.md), configured with `KEV_BASE_URL` (default `http://127.0.0.1:8009`). A stock server without the guard is rejected because it cannot provide the required coverage metadata.

See [client configuration](docs/clients.md) for coding agents, Hermes and Open WebUI. For HTTP, set `KEV_MCP_TOKEN` in the environment and run:

```sh
uv run kev-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Connect to `http://127.0.0.1:8000/mcp`. Remote access requires a reachable binding or reverse proxy, an explicit host allowlist and authentication. Use a private network or TLS for remote bearer authentication.

## Tools

| Tool | Purpose |
|---|---|
| `kev_store_document` | Store extracted text; return an immutable ID and source metadata |
| `kev_fetch_document` | Fetch public HTML/plain text and retain the extracted document |
| `kev_read_document` | Read a bounded line range |
| `kev_evaluate_document` | Ask typed questions about the whole document or an explicit line range |
| `kev_capabilities` | Read backend availability, loaded model identity and limits |

Example evaluation arguments:

```json
{
  "document_id": "ID_RETURNED_BY_STORE_OR_FETCH",
  "questions": {
    "billing": {"type": "noul", "instructions": "Does the customer report being charged twice?"},
    "team": {"type": "choice", "instructions": "Which team should handle this?",
             "criteria": {"billing": "Payments and refunds", "shipping": "Parcel delivery"}},
    "urgency": {"type": "score", "instructions": "How urgent does the customer say this is?",
                "criteria": ["Can wait", "Normal priority", "Urgent"]}
  }
}
```

Answers retain native fields: `noul` is a probability; `choice` includes option probabilities; `score` is an expected zero-based level. Confidence is not a measured accuracy rate. The calling agent handles explanations and synthesis.

Results include source/hash, full or partial coverage, token counts and actual model identity. The guard checks the complete upstream encoding before inference. Limits are 8,192 tokens per document-plus-question branch, 16,384 packed tokens and 16 questions per call. Oversized requests fail with useful counts. No text is silently truncated. Select fewer lines or submit fewer questions explicitly; partial results do not establish whole-document absence.

## Configuration and boundaries

| Variable | Default / meaning |
|---|---|
| `KEV_BASE_URL` | `http://127.0.0.1:8009`; guarded backend |
| `KEV_MODEL` | `kev-latest`; API alias, actual checkpoint returned separately |
| `KEV_API_KEY` | `local`; credential for a backend authentication proxy |
| `KEV_TIMEOUT` | `120` seconds; no automatic inference retries |
| `KEV_MCP_DB` | `~/.local/share/kev-mcp/store.sqlite3` |
| `KEV_MCP_TOKEN` | Optional on loopback; required for non-loopback HTTP |
| `KEV_MCP_HOST`, `KEV_MCP_PORT` | `127.0.0.1`, `8000` |
| `KEV_MCP_ALLOWED_HOSTS` | Comma-separated exact Host allowlist for wildcard binds/proxies |
| `KEV_MCP_ALLOWED_ORIGINS` | Comma-separated exact browser origins |
| `KEV_MAX_DOCUMENT_BYTES` | `2000000` UTF-8 bytes |
| `KEV_MAX_REQUEST_BODY_BYTES` | `4194304` MCP HTTP body bytes |

Each instance has one shared workspace: every authenticated client of that instance can access its documents. Use separate instances/stores for separate users. Documents persist; there is no retention scheduler or deletion tool in this version.

Fetching supports public HTTP(S) on ports 80/443, validated and pinned public addresses, bounded redirects and a 20-second deadline. Use an external extractor plus `kev_store_document` for PDFs, authenticated pages or browser rendering. Fetched content is source data, not instructions for the calling agent.

The runtime admits one request at a time. Concurrent calls get a busy error without entering a hidden queue. A timeout does not prove execution stopped; the bridge does not replay uncertain requests.

## Development

```sh
uv run ruff check .
uv run mypy src/kev_mcp
uv run pytest -q
uv build
```

Transport tests use the official MCP client and synthetic backend fixtures. The [acceptance runner](scripts/acceptance.py) exercises a real ROCm model. Maximum-context accuracy and sustained load remain unqualified. Open WebUI Knowledge IDs are not automatically imported into this store.
