"""Check two running HTTP services; repeat with --reuse to verify document persistence."""

import argparse
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from acceptance import CASES, QUESTIONS
from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client


@asynccontextmanager
async def connect(url, token):
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})

    @asynccontextmanager
    async def transport():
        async with streamable_http_client(url, http_client=http) as streams:
            yield streams

    try:
        async with Client(transport(), read_timeout_seconds=200) as client:
            yield client
    finally:
        await http.aclose()


async def call(client, name, arguments):
    started = time.perf_counter()
    result = await client.call_tool(name, arguments)
    assert not result.is_error, result.content
    return result.structured_content | {"end_to_end_ms": (time.perf_counter() - started) * 1000}


async def run(args):
    urls = [args.small_url, args.large_url]
    tokens = [os.environ["KEV_MCP_08B_TOKEN"], os.environ["KEV_MCP_4B_TOKEN"]]
    async with httpx.AsyncClient() as http:
        for url in urls:
            assert (await http.get(url)).status_code == 401
    async with connect(urls[0], tokens[0]) as small, connect(urls[1], tokens[1]) as large:
        clients = [small, large]
        caps = [await call(c, "kev_capabilities", {}) for c in clients]
        for c in clients:
            assert len((await c.list_tools()).tools) == 5
        if args.reuse:
            documents = json.loads(args.reuse.read_text())["documents"]
        else:
            documents = [
                await call(small, "kev_store_document", {"text": case[1], "title": case[0]})
                for case in CASES
            ]
        report = {"capabilities": caps, "documents": documents, "runs": []}
        for document, (expected, _, yes, urgency) in zip(documents, CASES, strict=True):
            for concurrent in (False, True):
                arguments = {"document_id": document["document_id"], "questions": QUESTIONS}
                if concurrent:
                    results = await asyncio.gather(
                        *(call(c, "kev_evaluate_document", arguments) for c in clients)
                    )
                else:
                    results = [await call(c, "kev_evaluate_document", arguments) for c in clients]
                for result in results:
                    answer = result["answers"]
                    assert answer["department"]["choice"] == expected, answer
                    assert (answer["double_charge"]["noul"] >= 0.5) is yes, answer
                    assert abs(answer["urgency"]["score"] - urgency) <= 0.15, answer
                    assert result["coverage"]["kind"] == "full"
                report["runs"].append(
                    {"case": expected, "simultaneous_models": concurrent, "results": results}
                )
        report["status"] = "passed"
        report["reused_documents"] = bool(args.reuse)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": "passed", "evaluations": 12, "reused": bool(args.reuse)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--small-url", default="http://127.0.0.1:8838/mcp")
    parser.add_argument("--large-url", default="http://127.0.0.1:8839/mcp")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse", type=Path)
    asyncio.run(run(parser.parse_args()))
