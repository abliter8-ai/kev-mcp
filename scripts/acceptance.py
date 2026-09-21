"""Finite real-model acceptance run. Writes checkpoints and always stops its runtime."""

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from kev_mcp.backend import Backend

QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this request?",
        "criteria": {
            "billing": "Charges, payments and refunds",
            "shipping": "Parcel delivery",
            "access": "Passwords and account login",
        },
    },
    "double_charge": {
        "type": "noul",
        "instructions": "Does the customer say they were charged twice?",
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent does the customer say this is?",
        "criteria": ["Can wait", "Normal priority", "Urgent, help immediately"],
    },
}
CASES = [
    (
        "billing",
        "I was charged twice for the same order. Both payments appear on my bank statement. "
        "This is urgent; I need help immediately.",
        True,
        2,
    ),
    (
        "shipping",
        "My parcel has not arrived. Tracking says it is delayed at the depot. "
        "Please check the delivery date. This can wait.",
        False,
        0,
    ),
    (
        "access",
        "I forgot my password and cannot log in. Please reset my password. Normal priority.",
        False,
        1,
    ),
]


async def exercise(args, base_url: str, report: dict, save):
    env = dict(
        os.environ,
        KEV_BASE_URL=base_url,
        KEV_MCP_DB=str(args.output.with_suffix(".sqlite3")),
        KEV_TIMEOUT="180",
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "kev_mcp.server"], env=env
    )

    async with Client(parameters, read_timeout_seconds=200) as client:

        async def call(name, arguments, expect_error=False):
            started = time.perf_counter()
            response = await client.call_tool(name, arguments)
            elapsed = (time.perf_counter() - started) * 1000
            if expect_error:
                assert response.is_error, f"{name} unexpectedly succeeded"
                return {"error": str(response.content), "end_to_end_ms": elapsed}
            assert not response.is_error, response.content
            result = response.structured_content
            assert isinstance(result, dict), response
            return result | {"end_to_end_ms": elapsed}

        report["capabilities"] = await call("kev_capabilities", {})
        save()
        for expected, text, yes, urgency in CASES:
            doc = await call("kev_store_document", {"text": text, "title": expected})
            assert "text" not in doc
            runs = []
            for _ in range(3):
                result = await call(
                    "kev_evaluate_document",
                    {
                        "document_id": doc["document_id"],
                        "questions": QUESTIONS,
                    },
                )
                answers = result["answers"]
                assert answers["department"]["choice"] == expected
                assert (answers["double_charge"]["noul"] >= 0.5) is yes
                assert abs(answers["urgency"]["score"] - urgency) <= 0.15
                assert result["coverage"]["kind"] == "full"
                runs.append(result)
            report.setdefault("cases", []).append({"expected": expected, "runs": runs})
            save()

        doc = await call("kev_store_document", {"text": CASES[0][1] + "\nDelivery can wait.\n"})
        followup = await call(
            "kev_evaluate_document",
            {
                "document_id": doc["document_id"],
                "questions": {"again": QUESTIONS["double_charge"]},
            },
        )
        assert followup["answers"]["again"]["noul"] > 0.5
        selection = await call(
            "kev_evaluate_document",
            {
                "document_id": doc["document_id"],
                "start_line": 2,
                "end_line": 2,
                "questions": {"again": QUESTIONS["double_charge"]},
            },
        )
        assert selection["coverage"]["kind"] == "partial"
        assert selection["answers"]["again"]["noul"] < 0.5
        report["followup"], report["selection"] = followup, selection
        save()

        fetched = await call(
            "kev_fetch_document",
            {
                "url": "https://raw.githubusercontent.com/jaredpalmer/kev/"
                "4f8110a3f8620cc3a182ae9a708e4398492c4b1a/README.md"
            },
        )
        assert "text" not in fetched and fetched["source_url"].startswith("https://")
        fetched_result = await call(
            "kev_evaluate_document",
            {
                "document_id": fetched["document_id"],
                "start_line": 1,
                "end_line": 25,
                "questions": {
                    "project": {
                        "type": "choice",
                        "instructions": "Which project is described?",
                        "criteria": {"Kev": None, "SQLite": None, "Linux": None},
                    }
                },
            },
        )
        assert fetched_result["answers"]["project"]["choice"] == "Kev"
        report["fetch_evaluate"] = fetched_result
        html = await call(
            "kev_fetch_document", {"url": "https://www.iana.org/help/example-domains"}
        )
        assert html["text_bytes"] > 0 and "text" not in html
        report["html_fetch"] = html
        save()

        long_text = "The following is an unrelated warehouse note.\n" * 128 + CASES[0][1]
        long_doc = await call("kev_store_document", {"text": long_text})
        long_result = await call(
            "kev_evaluate_document",
            {
                "document_id": long_doc["document_id"],
                "questions": {"charge": QUESTIONS["double_charge"]},
            },
        )
        assert long_result["answers"]["charge"]["noul"] > 0.5
        report["longer_input"] = long_result
        oversized = await call("kev_store_document", {"text": " x" * 9000})
        report["oversized_rejected"] = await call(
            "kev_evaluate_document",
            {
                "document_id": oversized["document_id"],
                "questions": {"q": QUESTIONS["double_charge"]},
            },
            expect_error=True,
        )
        assert "8192" in report["oversized_rejected"]["error"]
        save()

        # Token-boundary qualification is preflight-only: it does not claim 8K model accuracy.
        async with httpx.AsyncClient(base_url=base_url, timeout=30) as http:
            low, high = 0, 9000
            while low + 1 < high:
                mid = (low + high) // 2
                response = await http.post(
                    "/kev/preflight",
                    json={
                        "state": " x" * mid,
                        "questions": {"q": QUESTIONS["double_charge"]},
                    },
                )
                if response.status_code == 200:
                    low = mid
                else:
                    assert response.status_code == 422, response.text
                    high = mid
            accepted = await http.post(
                "/kev/preflight",
                json={
                    "state": " x" * low,
                    "questions": {"q": QUESTIONS["double_charge"]},
                },
            )
            rejected = await http.post(
                "/kev/preflight",
                json={
                    "state": " x" * high,
                    "questions": {"q": QUESTIONS["double_charge"]},
                },
            )
            assert accepted.status_code == 200 and rejected.status_code == 422
            report["token_boundary_preflight_only"] = {
                "accepted": accepted.json(),
                "rejected": rejected.json(),
            }
        save()

        backend = Backend(base_url, "kev-latest", timeout=180)
        concurrent = await asyncio.gather(
            *[backend.evaluate(long_text, {"q": QUESTIONS["double_charge"]}) for _ in range(4)],
            return_exceptions=True,
        )
        successes = [item for item in concurrent if isinstance(item, dict)]
        failures = [str(item) for item in concurrent if isinstance(item, Exception)]
        assert successes and failures and all("busy" in item for item in failures), failures
        recovery = await backend.evaluate(CASES[0][1], {"q": QUESTIONS["double_charge"]})
        assert recovery["answers"]["q"]["noul"] > 0.5
        report["contention"] = {
            "success_count": len(successes),
            "busy_errors": failures,
            "recovery": recovery,
        }
        save()


async def run(args):
    report = {
        "status": "running",
        "model_id": args.model_id,
        "checkpoint_revision": args.checkpoint_revision,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(args.output)

    save()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ)
    env.update(
        PYTHONPATH=os.pathsep.join(
            [str(Path(__file__).resolve().parents[1] / "src"), str(args.kev_source)]
        ),
        HF_HOME=str(args.hf_home),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        KEV_DATE_FACTS="0",
        KEV_DTYPE="bf16",
        TOKENIZERS_PARALLELISM="false",
    )
    command = [
        str(args.runtime_python),
        "-m",
        "kev_mcp.runtime",
        "--checkpoint",
        str(args.checkpoint),
        "--model-id",
        args.model_id,
        "--checkpoint-revision",
        args.checkpoint_revision,
        "--device",
        "rocm",
        "--port",
        str(port),
    ]
    base_url = f"http://127.0.0.1:{port}"
    with args.output.with_suffix(".runtime.log").open("w") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        try:
            async with httpx.AsyncClient(timeout=2) as http:
                for _ in range(240):
                    if process.poll() is not None:
                        raise RuntimeError("runtime exited before ready; inspect runtime log")
                    try:
                        response = await http.get(base_url + "/kev/capabilities")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
                else:
                    raise TimeoutError("runtime did not become ready within 240 seconds")
            await exercise(args, base_url, report, save)
            report["status"] = "passed"
        except BaseException as exc:
            report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            process.send_signal(signal.SIGINT) if process.poll() is None else None
            try:
                await asyncio.to_thread(process.wait, timeout=60)
            except subprocess.TimeoutExpired:
                report["cleanup_error"] = "runtime did not stop after SIGINT; inspect process"
            report["runtime_exit_code"] = process.poll()
            save()
    print(json.dumps({"status": report["status"], "output": str(args.output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-python", "kev-source", "checkpoint", "hf-home", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--checkpoint-revision", required=True)
    asyncio.run(run(parser.parse_args()))
