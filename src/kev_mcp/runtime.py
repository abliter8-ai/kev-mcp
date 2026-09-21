"""Strict, bounded launcher around pinned upstream Kev; GPU imports stay here."""

import argparse
import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from kev_mcp.schemas import validate_questions

UPSTREAM_REVISION = "4f8110a3f8620cc3a182ae9a708e4398492c4b1a"
CONTRACT = "kev-mcp-runtime-v1"


@dataclass(frozen=True)
class Limits:
    max_state: int = 8192
    max_branch: int = 8192
    max_packed: int = 16384
    max_questions: int = 16


def check_encoding(encoded: dict, question_ids: list[str], limits: Limits) -> dict:
    state = encoded["seg"].count(0)
    branches = {qid: state + encoded["seg"].count(i) for i, qid in enumerate(question_ids, 1)}
    if state > limits.max_state:
        raise ValueError(
            f"state: {state} tokens exceeds limit {limits.max_state}; select fewer lines"
        )
    for qid, count in branches.items():
        if count > limits.max_branch:
            raise ValueError(
                f"question {qid}: {count} tokens (state {state}, question {count - state}) "
                f"exceeds branch limit {limits.max_branch}; select fewer lines or reduce options"
            )
    packed = len(encoded["ids"])
    if packed > limits.max_packed:
        raise ValueError(
            f"packed request: {packed} tokens exceeds {limits.max_packed}; split questions"
        )
    if len(question_ids) > limits.max_questions:
        raise ValueError(f"question count exceeds {limits.max_questions}; split questions")
    return {
        "state_tokens": state,
        "branch_tokens": branches,
        "packed_tokens": packed,
        "state_truncated": False,
    }


class UpstreamEngine:
    def __init__(self, checkpoint: Path, model_id: str, checkpoint_revision: str, device: str):
        import kev
        import torch
        from kev import serve
        from kev.api import SystemOneRequest, to_record
        from kev.evaluate import load

        source_root = Path(kev.__file__).resolve().parent.parent
        revision = subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
        ).strip()
        if revision != UPSTREAM_REVISION:
            raise ValueError(f"Kev source must be pinned to {UPSTREAM_REVISION}")
        subprocess.run(
            ["git", "-C", str(source_root), "diff", "--exit-code", "HEAD", "--", "kev"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if serve.DATE_FACTS:
            raise ValueError("KEV_DATE_FACTS must be 0 so stored text is the evaluated state")
        if not (checkpoint / "head.pt").is_file():
            raise ValueError("checkpoint must contain head.pt; no fallback is permitted")
        if device == "rocm":
            if not torch.version.hip or not torch.cuda.is_available():
                raise ValueError("ROCm GPU unavailable; refusing fallback")
            target = "cuda"
        else:
            target = device
        tok, model = load(str(checkpoint), "cpu", dtype=torch.bfloat16)
        model.to(target)
        model.device = target
        if {parameter.device.type for parameter in model.parameters()} != {target}:
            raise ValueError("model parameters are not all on the requested device")
        torch.set_num_threads(4)
        if target == "cuda":
            torch.cuda.reset_peak_memory_stats()
        serve.STATE.update(
            tok=tok,
            model=model,
            dev=target,
            run=model_id,
            base=str(model.lm.config._name_or_path),
            lora=16,
        )
        self.serve, self.torch = serve, torch
        self.request_type, self.to_record = SystemOneRequest, to_record
        self.limits = Limits(max_state=serve.INFER_MAX_STATE, max_branch=serve.INFER_MAX_BRANCH)
        self.identity = {
            "model_id": model_id,
            "checkpoint_revision": checkpoint_revision,
            "source_revision": revision,
            "device": device,
            "torch": torch.__version__,
            "hip": torch.version.hip,
            "gpu": torch.cuda.get_device_name(0) if target == "cuda" else None,
        }

    def preflight(self, payload: dict) -> dict:
        request = self.request_type.model_validate(payload)
        record, _ = self.to_record(request)
        # Count the complete encoding. Limits are checked afterwards, before inference.
        encoded = self.serve.STATE["model"].encode(
            self.serve.STATE["tok"],
            record,
            max_state=sys.maxsize,
            max_branch=sys.maxsize,
            strict=True,
        )
        return check_encoding(encoded, list(request.questions), self.limits)

    def evaluate(self, payload: dict) -> dict:
        result = self.serve.systemone(self.request_type.model_validate(payload))
        if self.serve.STATE["dev"] == "cuda":
            result["memory"] = {
                "peak_allocated_bytes": self.torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": self.torch.cuda.max_memory_reserved(),
            }
        return result


def create_app(engine: Any, max_body_bytes: int = 2_100_000) -> FastAPI:
    app = FastAPI(title="Kev strict System One runtime", docs_url=None, redoc_url=None)
    admission = threading.Lock()

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        if request.method == "POST":
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > max_body_bytes:
                    return JSONResponse(
                        {"detail": "request body exceeds byte limit"}, status_code=413
                    )
            request._body = bytes(body)
        return await call_next(request)

    @app.get("/kev/capabilities")
    def capabilities():
        return {
            "contract": CONTRACT,
            "strict_input": True,
            "available": True,
            "question_types": ["noul", "choice", "score"],
            "limits": asdict(engine.limits),
            "runtime": engine.identity,
        }

    async def handle(request: Request, evaluate: bool):
        if not admission.acquire(blocking=False):
            raise HTTPException(503, "Kev is busy; no request was queued; retry later")
        try:
            try:
                payload = await request.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("state"), str):
                    raise ValueError("state must be document text")
                payload["questions"] = validate_questions(payload.get("questions"))
                accounting = await run_in_threadpool(engine.preflight, payload)
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from None
            if not evaluate:
                return {"token_accounting": accounting, "runtime": engine.identity}
            result = await run_in_threadpool(engine.evaluate, payload)
            return result | {"token_accounting": accounting, "runtime": engine.identity}
        finally:
            admission.release()

    @app.post("/kev/preflight")
    async def preflight(request: Request):
        return await handle(request, False)

    @app.post("/v1/systemone")
    async def systemone(request: Request):
        return await handle(request, True)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--checkpoint-revision", required=True)
    parser.add_argument("--device", choices=["rocm", "cuda", "mps", "cpu"], default="rocm")
    parser.add_argument("--port", type=int, default=8009)
    args = parser.parse_args()
    os.environ.setdefault("KEV_DTYPE", "bf16")
    engine = UpstreamEngine(args.checkpoint, args.model_id, args.checkpoint_revision, args.device)
    print(json.dumps({"runtime": engine.identity}), file=sys.stderr, flush=True)
    import uvicorn

    uvicorn.run(create_app(engine), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
