---
title: Kev dual-model service deployment
date: 2026-09-21
time: "18:35 UTC"
agent: Codex
status: SUCCESS
component: kev-mcp
target: Linux ROCm host
environment: personal
resource_group: local
plan_ref: ../b-implementation_plans/IP-002-durable-services.md
rollback_ref: ../durable-services.md#verify-and-recover
---

## Goal

Serve both Kev checkpoints durably and make both available in every Hermes profile.

## What deployed

| Artifact | Revision | Method |
|---|---|---|
| Kev native source | `4f8110a3f8620cc3a182ae9a708e4398492c4b1a` | Independent checkout and locked ROCm environment |
| Kev 0.8B | `225679690cdd1de6fceb1258b1bddf61c493cee9` | Verified adapter/base artifacts and offline cache |
| Kev 4B | `4bc64c6b4c4881148661ffb823ce21fcfdc79a0e` | Verified adapter/base artifacts and offline cache |
| MCP bridge | IP-002 release | Independent locked environment, two HTTP instances |

Exact portable service commands:

```sh
systemctl daemon-reload
systemctl enable kev-runtime@08b kev-runtime@4b kev-mcp@08b kev-mcp@4b
systemctl start kev-runtime@08b kev-runtime@4b kev-mcp@08b kev-mcp@4b
```

## Changes

Two model services, two bearer-authenticated loopback MCP endpoints, shared persistent SQLite store, startup readiness checks, 4B startup ordering, and automatic process restart. All 14 Hermes profiles received both connections and explicit tool selections. Eight running gateways used their native SIGUSR1 drain-and-restart path after configuration and after the acceptance restart.

## Verification

Four active/enabled units, native checkpoint identity checks, all 28 Hermes profile/server connections, and 24 synthetic dual-model evaluations across service restart passed. Original document IDs remained usable from either model. Local lint, type checks, 34 tests and package build passed. The final fleet console parity gate and deployed native residency readback passed. See CR-002 for timings and coverage limits.

## Issues

An initial bridge readiness race was fixed and the restart acceptance repeated successfully. Existing unrelated Hermes plugin failures were not changed. Fleet-console integration is recorded separately in the private fleet repository.

## Action required

None for using either model through the configured Hermes profiles. For an example, ask Hermes: “Use Kev 0.8B to check whether this text requests a refund, then compare with Kev 4B.”

## Related docs

- [CR-002](../c-completion_reports/CR-002-durable-services.md)
- [Service setup and rollback](../durable-services.md)
