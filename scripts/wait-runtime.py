"""Systemd readiness check: require the configured loaded checkpoint, not just a port."""

import json
import os
import time
import urllib.error
import urllib.request

deadline = time.monotonic() + 240
url = f"http://127.0.0.1:{os.environ['KEV_RUNTIME_PORT']}/kev/capabilities"
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = json.load(response)
        identity = body.get("runtime", {})
        if (
            body.get("strict_input") is True
            and body.get("available") is True
            and identity.get("model_id") == os.environ["KEV_MODEL_ID"]
            and identity.get("checkpoint_revision") == os.environ["KEV_CHECKPOINT_REVISION"]
        ):
            raise SystemExit(0)
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass
    time.sleep(1)
raise SystemExit("configured Kev checkpoint did not become ready")
