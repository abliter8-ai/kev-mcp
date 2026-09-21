import threading
import time

from fastapi.testclient import TestClient

from kev_mcp.runtime import Limits, check_encoding, create_app


def test_budget_boundaries_and_question_overhead():
    encoded = {"seg": [0] * 6 + [1] * 4 + [2] * 3, "ids": list(range(13))}
    limits = Limits(max_state=6, max_branch=10, max_packed=13, max_questions=2)
    assert check_encoding(encoded, ["first", "second"], limits)["branch_tokens"] == {
        "first": 10,
        "second": 9,
    }
    encoded["seg"].append(1)
    encoded["ids"].append(13)
    try:
        check_encoding(encoded, ["first", "second"], limits)
    except ValueError as exc:
        assert "first" in str(exc) and "11" in str(exc) and "10" in str(exc)
    else:
        raise AssertionError("oversized question was accepted")


class FakeEngine:
    identity = {"model_id": "fixture", "checkpoint_revision": "test"}
    limits = Limits()

    def __init__(self):
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False

    def preflight(self, payload):
        if payload["state"] == "oversized":
            raise ValueError("question billing: 8193 tokens exceeds branch limit 8192")
        return {"state_tokens": 4, "branch_tokens": {"q": 12}, "packed_tokens": 12}

    def evaluate(self, payload):
        self.calls += 1
        self.entered.set()
        if self.block:
            self.release.wait(5)
        return {
            "model": "kev-latest",
            "answers": {"q": {"type": "noul", "noul": 0.9}},
            "usage": {"input_tokens": 12, "output_tokens": 8},
            "latency_ms": 1,
        }


REQUEST = {
    "state": "text",
    "model": "kev-latest",
    "questions": {"q": {"type": "noul", "instructions": "Present?"}},
}


def test_native_endpoint_blocks_oversized_before_inference():
    engine = FakeEngine()
    with TestClient(create_app(engine)) as client:
        assert client.get("/kev/capabilities").json()["strict_input"] is True
        assert (
            client.post("/v1/systemone", json=REQUEST | {"state": "oversized"}).status_code == 422
        )
        assert engine.calls == 0
        result = client.post("/v1/systemone", json=REQUEST)
        assert result.status_code == 200
        assert result.json()["runtime"]["model_id"] == "fixture"
        assert result.json()["token_accounting"]["packed_tokens"] == 12


def test_overload_has_no_hidden_queue_and_recovers():
    engine = FakeEngine()
    engine.block = True
    with TestClient(create_app(engine)) as client:
        results = []
        first = threading.Thread(
            target=lambda: results.append(client.post("/v1/systemone", json=REQUEST))
        )
        first.start()
        assert engine.entered.wait(3)
        started = time.monotonic()
        second = client.post("/v1/systemone", json=REQUEST)
        assert second.status_code == 503
        assert time.monotonic() - started < 2
        engine.release.set()
        first.join(5)
        assert results[0].status_code == 200
        assert client.post("/v1/systemone", json=REQUEST).status_code == 200


def test_request_body_limit():
    with TestClient(create_app(FakeEngine(), max_body_bytes=100)) as client:
        result = client.post("/v1/systemone", content=b"x" * 101)
        assert result.status_code == 413
