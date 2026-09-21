"""Wait for authenticated MCP readiness and the configured runtime identity."""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client


async def main():
    url = f"http://127.0.0.1:{os.environ['KEV_MCP_PORT']}/mcp"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        http = create_mcp_http_client(
            headers={"Authorization": "Bearer " + os.environ["KEV_MCP_TOKEN"]}
        )

        @asynccontextmanager
        async def transport():
            async with streamable_http_client(url, http_client=http) as streams:
                yield streams

        try:
            async with Client(transport(), read_timeout_seconds=5) as client:
                response = await client.call_tool("kev_capabilities", {})
                body = response.structured_content or {}
                identity = body.get("runtime", {})
                if (
                    not response.is_error
                    and body.get("available") is True
                    and identity.get("model_id") == os.environ["KEV_MODEL_ID"]
                    and identity.get("checkpoint_revision") == os.environ["KEV_CHECKPOINT_REVISION"]
                ):
                    return
        except Exception:
            pass
        finally:
            await http.aclose()
        await asyncio.sleep(0.5)
    raise SystemExit("authenticated Kev MCP did not become ready")


asyncio.run(asyncio.wait_for(main(), timeout=40))
