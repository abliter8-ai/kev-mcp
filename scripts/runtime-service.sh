#!/usr/bin/env bash
set -euo pipefail
exec "${RUNTIME_PYTHON:?}" -m kev_mcp.runtime \
  --checkpoint "${KEV_CHECKPOINT:?}" \
  --model-id "${KEV_MODEL_ID:?}" \
  --checkpoint-revision "${KEV_CHECKPOINT_REVISION:?}" \
  --device "${KEV_DEVICE:-rocm}" --port "${KEV_RUNTIME_PORT:?}"
