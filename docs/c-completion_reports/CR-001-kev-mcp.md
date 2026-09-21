---
id: CR-001
plan: IP-001
date: 2026-09-21
status: draft
context_updated: true
---

# CR-001: Document tools for Kev over MCP

IP-001 is implemented. The bridge exposes five document/evaluation tools over stdio and authenticated Streamable HTTP. It uses the official TypeSafe SDK against a strict guard around pinned upstream Kev. Finite real-model acceptance passed with both 0.8B and 4B on ROCm. No permanent fleet service or route was created.

Context sync: matching IP-001 frontmatter status was updated to `complete`, and the new architecture is recorded in the AGENTS.md Evolution Log. No pre-existing KNOWN_ISSUES.md blocker was resolved; no such file existed in this new repository.

## Delivered behavior

- Immutable SQLite document IDs, hashes, source metadata, exact text retention and bounded line reads.
- Public HTML/plain-text fetching with bounded redirects, byte/time limits, validated public destinations and pinned connections preserving TLS hostname checks.
- Typed `noul`, `choice` and `score` evaluation by document ID, with explicit full/partial coverage and native probability fields.
- Actual-tokenizer preflight before inference; no silent state truncation. State, per-question branch, packed-input and question-count limits are checked.
- One admitted runtime request, immediate busy errors for contention, and no automatic inference retry after uncertain execution.
- Separate lightweight bridge and GPU environments, uv lockfile, package entry points, CI, client examples and portable real-model acceptance script.

## Validation

Local checks: `uv run ruff check .`, `uv run mypy src/kev_mcp`, `uv run pytest -q` and `uv build` passed. The suite has **34 passing tests**, including real subprocess stdio, real HTTP MCP-client calls, bearer/origin rejection, store isolation, fetch bounds, token-budget boundaries, native SDK round-trip, runtime overload and recovery. A Starlette dependency emits one deprecation warning for its AnyIO portal type alias. The built artifacts are a wheel and source distribution.

GitHub Actions runs the same commands from the lockfile on pushes and pull requests. The local results above do not depend on a CI run being available.

The ROCm runner called the real MCP subprocess and native SDK through an actual loopback HTTP runtime. Both models passed nine repeated classification requests (three cases, three question types), follow-up questions on retained IDs, selected-line evaluation, fetched-text evaluation, HTML extraction, a longer input, oversized rejection, contention and recovery.

| Measurement | Kev 0.8B | Kev 4B |
|---|---:|---:|
| Warm billing end-to-end | 155.0 ms | 625.4 ms |
| Warm shipping end-to-end | 159.5 ms | 596.0 ms |
| Warm account-access end-to-end | 156.3 ms | 572.0 ms |
| Warm model time, range across cases | 139.1–142.8 ms | 554.9–602.3 ms |
| 1,196-token request end-to-end | 891.8 ms | 4,085.4 ms |
| Peak PyTorch allocated memory during suite | 1.75 GiB | 8.49 GiB |
| Four simultaneous submissions | 1 completed, 3 busy errors | 1 completed, 3 busy errors |
| Request after contention | Passed | Passed |
| Runtime exit code | 0 | 0 |

Warm figures are medians of the second and third requests per case. Short requests contain 95–104 packed tokens and three questions. End-to-end includes MCP, SDK, HTTP and model work; model time is reported separately by Kev. These are small samples on reference PyTorch kernels, not an optimized performance ceiling or a controlled cold-start comparison.

Exact-boundary preflight accepted a branch of **8,192 tokens** (8,175 state plus 17 question tokens) and rejected **8,193** on both models. This check did not run inference at 8K. The largest inference input in this suite was the 1,196-token request. Broad accuracy, calibration, maximum-context inference and sustained multi-user load remain unqualified.

Both runtime processes exited, no acceptance/MCP process remained, and graphics reservation usage returned to 151,138,304 bytes. The trials changed no existing serving configuration.

## Evidence and reproduction

- [0.8B raw acceptance results](../f-reports_reviews/evidence/kev-08b.json)
- [4B raw acceptance results](../f-reports_reviews/evidence/kev-4b.json)
- [Finite acceptance runner](../../scripts/acceptance.py)
- [Runtime and ROCm setup](../runtime.md)
- [Client configuration](../clients.md)
- [Original baseline and pinned model/base revisions](../f-reports_reviews/2026-09-21-rocm-baseline.md)

Public results contain synthetic document metadata and public URLs. Private runtime logs and experiment paths remain in the operator's workspace. Source revision is checked at startup; checkpoint revision is operator-provided metadata backed by the previously checksum-verified archive used for these trials.

## Practical limits

One service instance is one shared workspace. Authentication does not create user-specific document isolation. Hermes and Open WebUI configuration is documented from current sources; neither application's interactive UI was part of this acceptance run. Open WebUI Knowledge IDs are not resolved automatically. PDF/browser/authenticated extraction requires an external extractor. Documents persist until operator cleanup.

Two defects found in real acceptance were corrected before the passing runs: MCP's default masking hid useful token-limit errors, and arbitrary DNS address order could select an unreachable IPv6 address. Expected errors now use MCP tool errors; fetching prefers IPv4 and can try another validated address within the original deadline.
