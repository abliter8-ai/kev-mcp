# Strict Kev runtime

The bridge and model runtime use separate Python environments. Install the bridge with its committed `uv.lock`. The runtime needs upstream Kev, local model artifacts and device-specific PyTorch. It does not download weights or fall back to another checkpoint/device.

## Upstream source and environment

The launcher requires source revision `4f8110a3f8620cc3a182ae9a708e4398492c4b1a` of [jaredpalmer/kev](https://github.com/jaredpalmer/kev). It checks Git identity and rejects tracked changes under `kev/`. Platform dependency changes in upstream `pyproject.toml` are permitted.

```sh
git clone https://github.com/jaredpalmer/kev.git
git -C kev checkout 4f8110a3f8620cc3a182ae9a708e4398492c4b1a
```

Prepare that checkout's environment using upstream's serving instructions and the correct PyTorch build for the device. Upstream's serving extra supplies FastAPI, Pydantic and uvicorn. Install this runtime code without replacing the established GPU dependencies:

```sh
uv pip install --python /path/to/kev/.venv/bin/python --no-deps /path/to/kev-mcp
```

Make the Kev source importable, for example with `PYTHONPATH=/path/to/kev`. Set `HF_HOME` to the local base-model cache. Use `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` for an offline model installation.

## Launch

```sh
/path/to/kev/.venv/bin/python -m kev_mcp.runtime \
  --checkpoint /path/to/kev-checkpoint \
  --model-id jaredpalmer/kev-0.8b \
  --checkpoint-revision 225679690cdd1de6fceb1258b1bddf61c493cee9 \
  --device rocm --port 8009
```

The checkpoint directory must contain the adapter configuration/weights and `head.pt`. It is not a standalone GGUF. The revision argument records operator-provided identity; use a verified Hub snapshot. It does not checksum the checkpoint files. Git source identity is checked at startup.

`rocm` requires HIP PyTorch and an available GPU. `cuda`, `mps` and `cpu` are explicit options, but the evidence here qualifies only ROCm. Loading merges LoRA on CPU, casts the backbone to BF16, keeps the pointer head FP32, then checks all parameters are on the requested device. CPU memory is needed during loading; GPU inference does not offload model layers to CPU.

The runtime binds only to loopback. Run the MCP bridge on the same host or use an authenticated tunnel. Routes:

| Route | Purpose |
|---|---|
| `POST /v1/systemone` | Native TypeSafe-compatible API plus strict preflight and metadata |
| `GET /kev/capabilities` | Loaded model identity and effective limits |
| `POST /kev/preflight` | Exact token counts without inference |

Keep date-fact augmentation disabled so evaluated state matches stored text. The guard uses upstream encoding with the loaded tokenizer, checks the complete input, then calls upstream inference. Invalid inputs return 422, oversized bodies 413 and a busy runtime 503. It admits one request at a time.

## Tested AMD environment

Radeon 890M (`gfx1150`), Python 3.12.13, PyTorch `2.8.0+rocm7.12.0`, Triton `3.4.0+rocm7.12.0`, Transformers `5.17.0`, PEFT `0.21.0`. No FLA or causal-conv1d acceleration was installed.

The isolated upstream project used Python `>=3.12,<3.13`, dependency `torch==2.8.0+rocm7.12.0`, and:

```toml
[[tool.uv.index]]
name = "amd"
url = "https://repo.amd.com/rocm/whl/gfx1150/"
ignore-error-codes = [403]

[tool.uv.sources]
torch = { index = "amd" }

[tool.uv]
environments = ["sys_platform == 'linux'"]
```

Resolution used `uv sync --extra serve --index-strategy unsafe-best-match`. The AMD index returns 403 for some absent packages; index selection affects transitive dependencies. This is the tested gfx1150 recipe, not a universal AMD wheel prescription. The [baseline](f-reports_reviews/2026-09-21-rocm-baseline.md) records exact model/base revisions.

## Finite acceptance run

From this project's checkout:

```sh
uv run python scripts/acceptance.py \
  --runtime-python /path/to/kev/.venv/bin/python \
  --kev-source /path/to/kev \
  --checkpoint /path/to/kev-checkpoint \
  --hf-home /path/to/hf-cache \
  --model-id jaredpalmer/kev-0.8b \
  --checkpoint-revision 225679690cdd1de6fceb1258b1bddf61c493cee9 \
  --output /path/to/results/kev-08b.json
```

The runner chooses a loopback port, starts the guard, and launches a real stdio MCP client. It tests synthetic decisions, repeated questions, selections, public fetching, longer input, oversized rejection, exact token-boundary preflight, contention and recovery. JSON checkpoints are written after each phase. Sibling `.runtime.log` and private `.sqlite3` files retain diagnostic state. In `finally`, it sends SIGINT to its own runtime and records the exit code. Rerunning restarts the finite suite; choose a new output name to preserve earlier evidence.

Maximum-context checks are explicitly preflight-only. They do not claim useful model accuracy or latency at 8K. Fetch tests require internet access even with offline model loading.
