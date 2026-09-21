# kev-mcp

A planned MCP interface for asking typed questions about documents with [Kev](https://github.com/jaredpalmer/kev).

**Status: design recorded; implementation pending approval.** No installable MCP server is published yet.

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

The first version targets a local Kev backend, stdio and Streamable HTTP MCP, and a private document store per service instance. Open WebUI connects as an MCP client; importing its existing Knowledge library is a separate integration.
