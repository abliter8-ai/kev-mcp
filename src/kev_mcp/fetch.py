"""Bounded extraction of public HTTP(S) documents."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import trafilatura


def _public_addresses(host: str) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
        if getattr(literal, "ipv4_mapped", None) is not None:
            raise ValueError("IPv4-mapped addresses are not supported")
        addresses = [str(literal)]
    except ValueError:
        try:
            addresses = list(
                {
                    str(item[4][0])
                    for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                }
            )
        except socket.gaierror as exc:
            raise ValueError(f"could not resolve host: {host}") from exc
    parsed = [ipaddress.ip_address(address) for address in addresses]
    if not parsed or any(
        getattr(item, "ipv4_mapped", None) is not None or not item.is_global for item in parsed
    ):
        raise ValueError("URL must resolve to a public address")
    return [str(item) for item in sorted(parsed, key=lambda item: item.version != 4)]


class _PinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self, ip: str):
        self.ip = ip
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        original_host = request.url.host
        request.url = request.url.copy_with(host=self.ip)
        request.headers["host"] = original_host
        if request.url.scheme == "https":
            request.extensions["sni_hostname"] = original_host
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def _validate_url(url: str) -> tuple[str, str, list[str]]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("only public HTTP(S) URLs without credentials are supported")
    if parsed.port not in (80, 443, None):
        raise ValueError("only HTTP ports 80 and 443 are supported")
    host = parsed.hostname
    if not host:
        raise ValueError("URL must include a host")
    if (
        parsed.scheme == "http"
        and parsed.port not in (None, 80)
        or parsed.scheme == "https"
        and parsed.port not in (None, 443)
    ):
        raise ValueError("URL scheme and port do not match")
    addresses = _public_addresses(host)
    return (
        urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")),
        host,
        addresses,
    )


async def _request(
    url: str, *, timeout_seconds: float, max_bytes: int, pinned_ip: str | None = None
) -> httpx.Response:
    if pinned_ip:
        normalized = url
        host = urlsplit(url).hostname or ""
        ip = pinned_ip
    else:
        normalized, host, addresses = await asyncio.to_thread(_validate_url, url)
        ip = addresses[0]
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(
        transport=_PinnedTransport(ip), timeout=timeout, follow_redirects=False, trust_env=False
    ) as client:
        async with client.stream(
            "GET", normalized, headers={"accept": "text/html, text/plain;q=0.9"}
        ) as response:
            if response.status_code >= 400:
                raise ValueError(f"fetch returned HTTP {response.status_code}")
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(f"response exceeds max_bytes ({content_length} > {max_bytes})")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"response exceeds max_bytes ({size} > {max_bytes})")
                chunks.append(chunk)
            headers = httpx.Headers(response.headers)
            headers.pop("content-encoding", None)
            headers["content-length"] = str(size)
            return httpx.Response(
                response.status_code,
                headers=headers,
                content=b"".join(chunks),
                request=response.request,
            )


async def _fetch_document(
    url: str, max_bytes: int = 2_000_000, timeout_seconds: float = 20
) -> dict:
    current = url
    deadline = time.monotonic() + timeout_seconds
    async with asyncio.timeout(timeout_seconds):
        for _ in range(6):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("document fetch exceeded timeout")
            normalized, _host, addresses = await asyncio.to_thread(_validate_url, current)
            response = None
            for address in addresses:
                try:
                    response = await asyncio.wait_for(
                        _request(
                            normalized,
                            timeout_seconds=remaining,
                            max_bytes=max_bytes,
                            pinned_ip=address,
                        ),
                        remaining,
                    )
                    break
                except httpx.ConnectError:
                    continue
            if response is None:
                raise ValueError("document fetch could not connect to a public address")
            if len(response.content) > max_bytes:
                raise ValueError(
                    f"response exceeds max_bytes ({len(response.content)} > {max_bytes})"
                )
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("redirect has no location")
                current = urljoin(current, location)
                continue
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type == "text/plain":
                text = response.content.decode(response.encoding or "utf-8")
                title = None
            elif content_type in {"text/html", "application/xhtml+xml"}:
                raw = response.content.decode(response.encoding or "utf-8", errors="replace")
                text, metadata = await asyncio.to_thread(_extract_html, raw)
                title = metadata.title if metadata else None
            else:
                raise ValueError(f"unsupported content type: {content_type or 'unknown'}")
            if not text.strip():
                raise ValueError("fetched document is empty")
            return {
                "text": text,
                "title": title,
                "source_url": current,
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        raise ValueError("too many redirects")


def _extract_html(raw: str):
    text = trafilatura.extract(raw, include_comments=False, include_tables=True) or ""
    return text, trafilatura.extract_metadata(raw)


async def fetch_document(url: str, max_bytes: int = 2_000_000, timeout_seconds: float = 20) -> dict:
    try:
        return await _fetch_document(url, max_bytes=max_bytes, timeout_seconds=timeout_seconds)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise ValueError("document fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise ValueError("document fetch failed while connecting to the public URL") from exc
