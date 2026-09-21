---
id: IP-001
title: Document tools for Kev over MCP
date: 2026-09-21
status: draft
---

# IP-001: Document tools for Kev over MCP

## Outcome

Hermes, coding agents and Open WebUI can fetch or submit document text, retain its ID, and ask typed questions through a local Kev model. Follow-up calls reuse the ID. Results preserve probabilities, source identity and the exact coverage evaluated. The repository contains a shareable implementation, setup instructions and measured evidence.

## Design

Use a Python MCP bridge with the official TypeSafe Python SDK pointed at a configured local Kev System One endpoint. Run the model in its own GPU environment. Reuse upstream Kev inference and schemas; do not rebuild its classifier or route requests to a general LLM adapter. A small launcher/guard in the model environment enforces strict encoding with the actual tokenizer and exposes input-budget and loaded-model information while preserving `/v1/systemone` compatibility.

This is preferred to embedding GPU dependencies in every MCP installation. A bare proxy would be smaller, but would not provide retained documents, extraction or explicit context coverage. A custom document UI would add scope before the underlying tool has been tested.

The initial model is the already-tested 0.8B checkpoint. The configured endpoint can use 4B without changing the tool contract. Model paths, revisions, URLs and credentials come from configuration. No automatic model substitution or cloud fallback.

### Tools

| Tool | Input | Result |
|---|---|---|
| `kev_store_document` | Text, optional title and source URL | Immutable document ID, content hash and metadata |
| `kev_fetch_document` | Public HTTP(S) URL | Extracted HTML/plain-text document stored under an ID, final source URL and fetch time |
| `kev_read_document` | Document ID, optional line range | Metadata and bounded text with stable line numbers |
| `kev_evaluate_document` | Document ID, typed questions, optional explicit line range | Native typed answers and probabilities, source metadata, coverage, token accounting and model identity |
| `kev_capabilities` | None | Backend availability, loaded model identity, supported question types and effective input limits |

Question types retain upstream `noul`, `choice` and `score` semantics. A yes/no probability is not automatically a proven fact, and choice confidence is not an accuracy percentage. Tool descriptions explain these semantics to callers. The bridge does not invent quotes or explanations from classification results.

### Document and runtime boundaries

- Store documents locally in SQLite, with immutable IDs and content hashes. Return metadata by default so full documents do not enter the caller's context unnecessarily.
- Use one private store per instance. Authenticated Streamable HTTP callers of that instance share its workspace; this is not per-user isolation. Use separate instances for separate trust boundaries. Stdio uses the local caller's instance.
- Support bounded public HTML/plain-text fetching. Check destinations, redirects and resolved addresses, and limit response bytes and duration. Other extractors can submit text through the store tool. PDF, browser automation and authenticated page fetching are outside this first version.
- Preserve the complete extracted document. Reject evaluation when the document plus any question/options exceeds the backend's strict branch limit. Return counts and the offending question. An explicit line selection is permitted and marked as partial coverage; do not silently truncate or claim whole-document conclusions from chunks.
- Reuse upstream encoding for exact checks. Check packed-request size and question count as operational limits as well as the per-branch context bound. Serialize GPU work with bounded admission; surface overload and timeout errors without replaying unknown requests automatically.
- Keep the model endpoint on loopback for the initial trial. Streamable HTTP requires configured authentication outside loopback. Credentials and documents stay outside Git. Protect stdio framing by writing logs to stderr.

## Implementation sequence

1. **Package and configuration.** Create the Python project, lock dependencies and record exact upstream revisions. Separate bridge dependencies (MCP SDK, TypeSafe SDK, HTTP client and HTML extractor) from the optional Kev runtime environment. Add documented entry points and environment-based configuration.
2. **Document tools.** Implement SQLite storage, immutable IDs, source metadata, line reads and bounded URL extraction. Test preservation, invalid IDs, extraction and fetch bounds.
3. **Native Kev integration.** Add the minimal strict-preflight runtime guard using upstream conversion and encoding. Connect the bridge with the official SDK. Test request/response compatibility for all three question types and fail clearly on missing or mismatched backend capabilities.
4. **MCP interface.** Expose the five tools over stdio and Streamable HTTP with structured output, useful errors, authentication and explicit coverage. Test with a real MCP client over both transports.
5. **ROCm acceptance trial.** Use the existing isolated environment and archived weights for finite 0.8B and 4B tests. Exercise fetch/store/evaluate, follow-up questions, explicit selections, within-budget and oversized inputs, and bounded contention. Record actual end-to-end latency separately from model timing, memory, correctness and recovery. Keep backend binding local and leave no persistent process after the trial.
6. **Client documentation and examples.** Provide Hermes/coding-agent stdio examples and Open WebUI Streamable HTTP setup. Label client-specific smoke tests as tested only when executed. Explain that Open WebUI Knowledge IDs are not automatically document IDs in this service. Include a portable evaluation runner and synthetic fixtures.
7. **Verify and publish.** Run the focused unit/integration suite, lint and type checks; review the staged diff for secrets and private data. Publish code, lockfiles, CI, usage docs and CR-001 with exact evidence and limitations to this repository.

## Acceptance criteria

- A real MCP client can store a document, receive an ID and make two independent evaluations with that ID against Kev on ROCm.
- All three native question types pass through the official SDK and retain their native answer fields.
- URL extraction stores content without returning the full text by default. Results identify the stored source and hash.
- Oversized inputs fail before model inference with useful budget information. Tests cover exact-boundary behavior, question overhead and partial selections. No successful result hides truncated coverage.
- Both transports pass real client tests. HTTP authentication rejects unauthorized requests. Independent service stores cannot resolve each other's document IDs.
- 0.8B and 4B trials record checkpoint revisions, runtime, input sizes, expected decisions, latency and peak memory. Failures or unqualified workloads are reported directly.
- Repository checks and a public synthetic reproduction path are available. No credentials, private documents or internal host addresses are committed.

## Scope of approval

Approval covers the dependencies and implementation above, finite tests in the existing isolated ROCm workspace, and publishing the results to this repository. It does not add a permanent fleet service, change production routes, automatically import Open WebUI libraries, or build a new UI. A persistent deployment needs a separate explicit instruction.

## Evidence

- [TypeSafe integration findings](../f-reports_reviews/2026-09-21-typesafe-integration.md)
- [Measured ROCm baseline](../f-reports_reviews/2026-09-21-rocm-baseline.md)
- [Kev upstream](https://github.com/jaredpalmer/kev)
- [Official TypeSafe Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
