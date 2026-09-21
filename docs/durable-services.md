# Durable services for both models

The systemd templates in `deploy/systemd/` run two independent native runtimes and two authenticated HTTP MCP bridges. Both bridges can share one SQLite document store. A document ID returned by either endpoint then works on both. All clients of that store share access to its documents.

| Instance | Runtime, loopback | MCP, loopback | Checkpoint |
|---|---|---|---|
| `08b` | `8038` | `8838/mcp` | `jaredpalmer/kev-0.8b` |
| `4b` | `8039` | `8839/mcp` | `jaredpalmer/kev-4b` |

## Installation layout

Choose a service account and a permanent service root, for example `/srv/services/kev-mcp`. Keep releases under `releases/`, with `current` pointing to the selected release. Store the pinned upstream checkout in `upstream/`, its independent Python environment in `runtime-venv/`, and the bridge environment in `bridge-venv/`. Keep verified adapters/base models under `weights/`, the offline Hugging Face cache under `hf/`, and private documents under `data/`.

Follow [runtime preparation](runtime.md) for source, model and ROCm pins. Copy the artifacts into the permanent layout; do not leave symlinks to experiment directories. Install both environments from their lockfiles. The runtime's platform-specific lockfile belongs beside its upstream project. Keep the bridge's committed lockfile separate.

Render `@SERVICE_ROOT@` and `@SERVICE_USER@` in the two `.service.in` templates, and install them as `/etc/systemd/system/kev-runtime@.service` and `kev-mcp@.service`. Install `4b-ordering.conf` as `/etc/systemd/system/kev-runtime@4b.service.d/ordering.conf`. This orders startup so both CPU model merges do not start together.

Create `/etc/kev-mcp/common.env`, readable only by root and the service account. Substitute your permanent root:

```ini
RUNTIME_PYTHON=/srv/services/kev-mcp/runtime-venv/bin/python
BRIDGE_PYTHON=/srv/services/kev-mcp/bridge-venv/bin/python
PYTHONPATH=/srv/services/kev-mcp/current/src:/srv/services/kev-mcp/upstream
HF_HOME=/srv/services/kev-mcp/hf
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
KEV_DTYPE=bf16
KEV_DATE_FACTS=0
TOKENIZERS_PARALLELISM=false
KEV_DEVICE=rocm
KEV_MCP_DB=/srv/services/kev-mcp/data/documents.sqlite3
KEV_MCP_HOST=127.0.0.1
KEV_TIMEOUT=180
KEV_MODEL=kev-latest
```

Create `08b.env` in the same directory:

```ini
KEV_CHECKPOINT=/srv/services/kev-mcp/weights/kev-0.8b
KEV_MODEL_ID=jaredpalmer/kev-0.8b
KEV_CHECKPOINT_REVISION=225679690cdd1de6fceb1258b1bddf61c493cee9
KEV_RUNTIME_PORT=8038
KEV_BASE_URL=http://127.0.0.1:8038
KEV_MCP_PORT=8838
KEV_MCP_TOKEN=REPLACE_WITH_HOST_GENERATED_SECRET
```

For `4b.env`, use `weights/kev-4b`, model ID `jaredpalmer/kev-4b`, revision `4bc64c6b4c4881148661ffb823ce21fcfdc79a0e`, runtime port `8039` and MCP port `8839`. Generate a distinct token for each endpoint on the service host, and write it directly into its protected environment file. Keep tokens out of repositories, shell history and logs. Use directory mode `0750`, environment file mode `0640` with the service account's group, and data directory mode `0700`.

Enable and start the four units after `systemctl daemon-reload`. The runtime start job waits for the configured checkpoint identity and readiness, not just an open port. Units restart on process exit. Read logs with `journalctl -u kev-runtime@08b` (and the corresponding other units). A process restart is covered by acceptance; reboot recovery depends on systemd enablement and is not a claimed power-cycle test.

## Hermes

Back up each profile's `config.yaml` and `.env` on the host before editing. Add these server definitions while preserving existing entries:

```yaml
mcp_servers:
  kev-08b:
    url: http://127.0.0.1:8838/mcp
    headers:
      Authorization: Bearer ${KEV_MCP_08B_TOKEN}
    timeout: 180
    connect_timeout: 20
    enabled: true
    supports_parallel_tool_calls: false
  kev-4b:
    url: http://127.0.0.1:8839/mcp
    headers:
      Authorization: Bearer ${KEV_MCP_4B_TOKEN}
    timeout: 180
    connect_timeout: 20
    enabled: true
    supports_parallel_tool_calls: false
```

Set those two variables in the profile's private `.env`. Where a profile uses explicit `toolsets` or `platform_toolsets` allowlists, append `mcp-kev-08b` and `mcp-kev-4b`. Reload through the installed Hermes version's supported MCP reload or graceful gateway restart path. A gateway's active status alone does not prove tool availability: test discovery and an actual evaluation with each profile's native MCP client.

These loopback URLs work when Hermes runs on the same host. A remote client needs a private authenticated proxy/tunnel and appropriate host/origin settings; see [client connections](clients.md).

## Verify and recover

With the two token variables available to the acceptance process:

```sh
uv run python scripts/service-acceptance.py --output /private/before.json
```

This checks bearer rejection, discovery, shared IDs, three synthetic cases with three question types, and serial plus simultaneous evaluation on both loaded models. Restart all four units, then verify the saved IDs still work:

```sh
uv run python scripts/service-acceptance.py --reuse /private/before.json --output /private/after.json
```

Each phase performs 12 evaluations. These are bounded synthetic checks, not sustained-load or maximum-context qualification. Existing limits still apply, including one admitted request per runtime and immediate busy responses.

For rollback, gracefully stop and disable the four units; restore the saved Hermes profile configurations and private environment files, then reload those clients. To revert a code release, repoint `current` to the previous release and restart the units. Preserve `data/`, weights, environment files and backups. Do not remove document databases during rollback.
