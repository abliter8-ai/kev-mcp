---
id: IP-002
title: Durable dual-model services and Hermes connections
date: 2026-09-21
status: complete
---

# IP-002: Durable dual-model services

Authorised by David on 2026-09-21: “Yes lets do that. Build it durably for both models.” Scope clarified: “Add them to all Hermes profiles.” This includes installation, service startup, profile configuration and verification.

1. Install pinned code, independent runtime environments, both checkpoint/base pairs and offline caches under a durable service root.
2. Add enabled systemd services for both ROCm runtimes and two authenticated MCP endpoints, with restart policies and one shared private document store.
3. Register both native runtime identities in fleet recipes, runtime probing and planner inventory; retain all unrelated configuration.
4. Back up every Hermes profile configuration, add both MCP connections, reload through supported mechanisms and test native discovery and evaluation.
5. Check both models together, cross-model document-ID reuse, restart recovery and persistent stored documents. Record resource use and bounded latency.
6. Publish portable service templates, setup/rollback instructions and deployment evidence. Keep host-specific paths, credentials and profiles out of the public repository.

The prior 8,192-token branch limit remains unchanged. Qualification remains bounded to the tested requests; this deployment does not imply sustained-load or maximum-context accuracy qualification. Profile configurations and new service units have explicit rollback paths. No unrelated service or model is replaced.
