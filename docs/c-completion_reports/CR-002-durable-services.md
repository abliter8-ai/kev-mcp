---
id: CR-002
plan: IP-002
date: 2026-09-21
status: draft
context_updated: true
---

# CR-002: Durable dual-model services

Both models now run as independent native ROCm services with authenticated HTTP MCP bridges and a shared persistent document store. Four systemd units are enabled, with process restart policies and readiness checks that verify the configured checkpoint. The code, runtime environments, checkpoints, base models and offline caches use permanent paths independent of the earlier experiments.

All 14 Hermes profile configurations contain both connections and explicit tool selections. Each profile passed discovery of five tools per model and a real document evaluation through its installed Hermes MCP client. All eight running gateways reloaded through Hermes's native drain-and-restart mechanism. Profile configurations and credentials were backed up on the host; no credentials or private profile data are published here.

## Evidence

- `uv run ruff check .`: passed.
- `uv run mypy src/kev_mcp`: passed for eight source files.
- `uv run pytest -q`: 34 passed; one existing dependency deprecation warning.
- `uv build`: wheel and source distribution built.
- `scripts/service-acceptance.py`: 12 evaluations passed before restart and 12 after restart using the original document IDs. Three cases covered choice, yes/no probability and ordered score. Serial and simultaneous requests used both loaded models. Both endpoints rejected unauthenticated access and exposed five tools.
- Native Hermes checks: 28 profile/server connections passed discovery and real evaluation, repeated after service restart; both toolsets were included in each profile's effective API selection.
- Four service units read back as active and enabled. Permanent layout has no symlinks into experiment directories. Source revision and environment lockfile hashes are retained in the private deployment record.
- Fleet integration passed the complete console parity gate: planner tests/typecheck,
  fresh observations, native residency agreement across 38 lanes, and deployed console
  readback. The deployed console reports both Kev identities from their native
  capabilities endpoints. Planner drift was zero at final acceptance.
- Published through [PR #1](https://github.com/abliter8-ai/kev-mcp/pull/1); branch,
  pull-request and merged-main CI checks passed. Deployed files were checked against
  the published Git revision.

Public synthetic evidence: [before restart](../f-reports_reviews/evidence/durable-before.json) and [after restart](../f-reports_reviews/evidence/durable-after.json).

| Post-restart median end-to-end, three short cases | 0.8B | 4B |
|---|---:|---:|
| Serial calls with both models resident | 166.2 ms | 665.0 ms |
| Simultaneous calls to both models | 384.5 ms | 774.1 ms |

The shared GPU shows contention. These small samples establish operation together; they do not establish sustained capacity or an optimized latency ceiling. Host available memory was approximately 13 GiB with both services running. Other applications were also resident, so this is a host snapshot rather than model-only memory attribution.

## Corrections and limits

The first immediate post-restart client attempt found that a bridge's `Type=exec` startup could complete before HTTP was ready. Added an authenticated MCP `ExecStartPost` check and repeated the full restart/persistence phase successfully. Readiness now checks model ID and checkpoint revision through `kev_capabilities`.

Hermes can park an MCP connection while its server restarts; the running gateways were gracefully reloaded after the restart test. Native profile-client and effective-toolset checks establish integration. Autonomous tool selection by every configured chat model was not evaluated. The current Hermes `/v1/toolsets` endpoint lists built-in/plugin checklist entries and omits MCP entries, so it was not used as an MCP availability verdict.

The prior 8,192-token branch and 16,384 packed-token limits remain. Full-context inference accuracy, sustained multi-user load, and power-cycle recovery remain unqualified. Systemd enablement was verified; no host reboot was performed. Open WebUI remains documented configuration guidance.

## Operation and context

[Durable setup and rollback](../durable-services.md) records portable paths, environment settings, unit installation, Hermes connections and retained-data recovery. Context sync: matching IP-002 frontmatter status was updated to `complete`. AGENTS.md records the new service architecture. No pre-existing KNOWN_ISSUES.md blocker was resolved; no such file exists in this repository.
