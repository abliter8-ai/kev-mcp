import asyncio
import os
import socket
import sys
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from kev_mcp.config import Settings
from kev_mcp.documents import DocumentStore
from kev_mcp.server import _http_app, create_server


class FakeBackend:
    def __init__(self):
        self.calls = []

    async def capabilities(self):
        return {
            "available": True,
            "model": "fake",
            "supported_questions": ["noul", "choice", "score"],
        }

    async def evaluate(self, state, questions):
        self.calls.append((state, questions))
        return {
            "native_answers": {"q1": {"answer": True}},
            "usage": {"input_tokens": 2},
            "model": "fake",
        }


class FakeStore:
    def __init__(self):
        self.items = {}

    def store(self, text, title=None, source_url=None, fetched_at=None):
        metadata = {"id": "doc-1", "title": title, "source_url": source_url, "content_hash": "abc"}
        self.items["doc-1"] = (metadata, text)
        return metadata

    def select(self, document_id, start_line=None, end_line=None):
        metadata, text = self.items[document_id]
        lines = text.splitlines()
        start = start_line or 1
        end = end_line or len(lines)
        return {
            "document": metadata,
            "text": "\n".join(lines[start - 1 : end]),
            "coverage": {
                "kind": "partial" if start_line or end_line else "full",
                "start_line": start,
                "end_line": end,
                "total_lines": len(lines),
            },
        }

    def read(self, document_id, start_line=None, end_line=None, max_chars=16000):
        result = self.select(document_id, start_line, end_line)
        result["text"] = result["text"][:max_chars]
        return result


@pytest.mark.asyncio
async def test_server_exposes_five_tools_and_evaluates_selected_coverage(tmp_path):
    backend = FakeBackend()
    store = FakeStore()
    server = create_server(backend=backend, store=store)

    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "kev_store_document",
        "kev_fetch_document",
        "kev_read_document",
        "kev_evaluate_document",
        "kev_capabilities",
    }
    descriptions = {tool.name: tool.description for tool in tools}
    assert all(descriptions.values())
    assert "probabilities" in descriptions["kev_evaluate_document"]
    assert "partial" in descriptions["kev_evaluate_document"]

    stored = await server.call_tool("kev_store_document", {"text": "one\ntwo", "title": "T"})
    assert stored.structured_content["id"] == "doc-1"
    result = await server.call_tool(
        "kev_evaluate_document",
        {
            "document_id": "doc-1",
            "questions": {"q1": {"type": "noul", "instructions": "Is this so?"}},
            "start_line": 2,
            "end_line": 2,
        },
    )
    output = result.structured_content
    assert output["coverage"]["kind"] == "partial"
    assert output["coverage"]["start_line"] == 2
    assert backend.calls[0][0] == "two"


@pytest.mark.asyncio
async def test_server_keeps_full_text_for_evaluation_by_default():
    backend = FakeBackend()
    store = FakeStore()
    server = create_server(backend=backend, store=store)
    await server.call_tool("kev_store_document", {"text": "one\ntwo"})
    await server.call_tool(
        "kev_evaluate_document",
        {"document_id": "doc-1", "questions": {"q1": {"type": "noul", "instructions": "Q"}}},
    )
    assert backend.calls[0][0] == "one\ntwo"


@pytest.mark.asyncio
async def test_stdio_subprocess_uses_real_store_and_returns_backend_error(tmp_path):
    env = dict(os.environ)
    env.update(
        {
            "KEV_MCP_DB": str(tmp_path / "stdio.sqlite3"),
            "KEV_BASE_URL": "http://127.0.0.1:1",
            "KEV_MODEL": "fake",
        }
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "kev_mcp.server"],
        env=env,
    )
    async with Client(params) as client:
        stored = await client.call_tool(
            "kev_store_document", {"text": "stdio text", "title": "Test"}
        )
        assert stored.structured_content["document_id"]
        read = await client.call_tool(
            "kev_read_document", {"document_id": stored.structured_content["document_id"]}
        )
        assert read.structured_content["text"] == "stdio text"
        failed = await client.call_tool("kev_capabilities", {})
        assert failed.is_error
        assert "backend unavailable" in failed.content[0].text.lower()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_streamable_http_real_client_auth_and_coverage(tmp_path):
    port = _free_port()
    settings = Settings(
        base_url="http://127.0.0.1:1",
        model="fake",
        api_key="local",
        db_path=tmp_path / "http.sqlite3",
        host="127.0.0.1",
        port=port,
        token="secret-token",
    )
    backend = FakeBackend()
    app = _http_app(
        settings, create_server(settings, backend=backend, store=DocumentStore(settings.db_path))
    )
    config = uvicorn.Config(app, host=settings.host, port=port, log_level="error")
    uvicorn_server = uvicorn.Server(config)
    task = asyncio.create_task(uvicorn_server.serve())
    try:
        for _ in range(100):
            if uvicorn_server.started:
                break
            await asyncio.sleep(0.01)
        url = f"http://127.0.0.1:{port}/mcp"
        async with httpx.AsyncClient() as raw:
            assert (await raw.get(url)).status_code == 401
            assert (await raw.delete(url)).status_code == 401
            assert (
                await raw.get(
                    url,
                    headers={"Authorization": "Bearer secret-token", "Origin": "http://evil.test"},
                )
            ).status_code == 403

        http_client = create_mcp_http_client(headers={"Authorization": "Bearer secret-token"})

        @asynccontextmanager
        async def transport():
            async with streamable_http_client(url, http_client=http_client) as streams:
                yield streams

        async with Client(transport()) as client:
            listed = await client.list_tools()
            assert len(listed.tools) == 5
            stored = await client.call_tool("kev_store_document", {"text": "one\ntwo"})
            doc_id = stored.structured_content["document_id"]
            result = await client.call_tool(
                "kev_evaluate_document",
                {
                    "document_id": doc_id,
                    "questions": {"q1": {"type": "noul", "instructions": "Is this so?"}},
                    "start_line": 2,
                    "end_line": 2,
                },
            )
            assert result.structured_content["coverage"]["kind"] == "partial"
            assert backend.calls[-1][0] == "two"
        await http_client.aclose()
    finally:
        uvicorn_server.should_exit = True
        await task
