from datetime import datetime, timezone

import httpx
import pytest

from kev_mcp import fetch as fetch_module


@pytest.fixture(autouse=True)
def fake_public_dns(monkeypatch):
    def resolve(host):
        if host in {"127.0.0.1", "::1"}:
            raise ValueError("URL must resolve to a public address")
        return ["93.184.216.34"]

    monkeypatch.setattr(fetch_module, "_public_addresses", resolve)


@pytest.mark.asyncio
async def test_fetch_plain_text_preserves_content_and_final_url(monkeypatch):
    async def fake_request(url, **kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=utf-8"},
            content=b"hello\n",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(fetch_module, "_request", fake_request)
    result = await fetch_module.fetch_document("https://example.test/start")

    assert result["text"] == "hello\n"
    assert result["source_url"] == "https://example.test/start"
    datetime.fromisoformat(result["fetched_at"].replace("Z", "+00:00")).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_fetch_extracts_html_and_rejects_empty_or_unsupported(monkeypatch):
    async def html(url, **kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=(
                b"<html><title>Title</title><body><article>Readable text</article></body></html>"
            ),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(fetch_module, "_request", html)
    result = await fetch_module.fetch_document("https://example.test/page")
    assert result["text"] == "Readable text"
    assert result["title"] == "Title"

    async def empty(url, **kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"   ",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(fetch_module, "_request", empty)
    with pytest.raises(ValueError, match="empty"):
        await fetch_module.fetch_document("https://example.test/empty")

    async def binary(url, **kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(fetch_module, "_request", binary)
    with pytest.raises(ValueError, match="unsupported"):
        await fetch_module.fetch_document("https://example.test/file.pdf")


@pytest.mark.asyncio
async def test_fetch_rejects_private_hosts_and_response_limit(monkeypatch):
    with pytest.raises(ValueError, match="public"):
        await fetch_module.fetch_document("http://127.0.0.1/")

    async def oversized(url, **kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "10"},
            content=b"0123456789",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(fetch_module, "_request", oversized)
    with pytest.raises(ValueError, match="max_bytes"):
        await fetch_module.fetch_document("https://example.test/", max_bytes=5)


@pytest.mark.asyncio
async def test_fetch_redirect_to_private_host_is_rejected(monkeypatch):
    async def redirect(url, **kwargs):
        return httpx.Response(
            302, headers={"location": "http://127.0.0.1/"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(fetch_module, "_request", redirect)
    with pytest.raises(ValueError, match="public"):
        await fetch_module.fetch_document("https://example.test/")


@pytest.mark.asyncio
async def test_fetch_timeout_is_bounded(monkeypatch):
    async def slow(url, **kwargs):
        await __import__("asyncio").sleep(1)

    monkeypatch.setattr(fetch_module, "_request", slow)
    with pytest.raises(ValueError, match="timed out"):
        await fetch_module.fetch_document("https://example.test/", timeout_seconds=0.01)


@pytest.mark.asyncio
async def test_fetch_retries_next_validated_address_after_connect_failure(monkeypatch):
    attempts = []

    async def request(url, **kwargs):
        attempts.append(kwargs["pinned_ip"])
        if len(attempts) == 1:
            raise httpx.ConnectError("first address unavailable")
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"ok",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(
        fetch_module, "_public_addresses", lambda host: ["93.184.216.34", "2001:db8::1"]
    )
    monkeypatch.setattr(fetch_module, "_request", request)
    result = await fetch_module.fetch_document("https://example.test/")

    assert result["text"] == "ok"
    assert attempts == ["93.184.216.34", "2001:db8::1"]
