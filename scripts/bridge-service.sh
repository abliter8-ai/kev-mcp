#!/usr/bin/env bash
set -euo pipefail
exec "${BRIDGE_PYTHON:?}" -m kev_mcp.server --transport streamable-http
