import pytest

from kev_mcp.schemas import validate_questions


def test_question_contract_requires_valid_options():
    questions = validate_questions(
        {
            "yes": {"type": "noul", "instructions": "Present?"},
            "choice": {"type": "choice", "instructions": "Which?", "criteria": {"a": None}},
            "rating": {"type": "score", "instructions": "Level?", "criteria": ["low", "high"]},
        }
    )
    assert questions["yes"]["type"] == "noul"
    for invalid in [{}, {"x": {"type": "score", "instructions": "Level?", "criteria": ["low"]}}]:
        with pytest.raises(ValueError):
            validate_questions(invalid)


@pytest.mark.asyncio
async def test_official_sdk_round_trip_and_no_retry():
    import asyncio
    import socket
    import threading

    import uvicorn
    from test_runtime import REQUEST, FakeEngine

    from kev_mcp.backend import Backend
    from kev_mcp.runtime import create_app

    engine = FakeEngine()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(engine), log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started
        backend = Backend(f"http://127.0.0.1:{port}", "kev-latest", timeout=5)
        result = await backend.evaluate("text", REQUEST["questions"])
        assert result["answers"]["q"]["noul"] == 0.9
        assert result["runtime"]["model_id"] == "fixture"
        assert result["token_accounting"]["packed_tokens"] == 12
        with pytest.raises(ValueError, match="8193"):
            await backend.evaluate("oversized", REQUEST["questions"])
        assert engine.calls == 1
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
