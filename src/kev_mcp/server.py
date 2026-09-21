"""MCP tools and transport launcher for the local Kev service."""

from __future__ import annotations

import argparse
import hmac
import logging
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from .config import Settings, _is_loopback
from .documents import DocumentStore
from .fetch import fetch_document
from .schemas import Questions, validate_questions

logger = logging.getLogger("kev_mcp")


def create_server(
    settings: Settings | None = None,
    backend: Any | None = None,
    store: Any | None = None,
) -> MCPServer:
    """Build an MCP server. Dependencies are injectable for portable tests."""
    settings = settings or Settings.from_env()
    if store is None:
        store = DocumentStore(settings.db_path, max_bytes=settings.max_document_bytes)
    if backend is None:
        from .backend import Backend

        backend = Backend(settings.base_url, settings.model, settings.timeout, settings.api_key)

    server = MCPServer(
        name="kev-mcp", version="0.1.0", description="Document decisions with local Kev inference"
    )

    @server.tool(name="kev_store_document", structured_output=True)
    def store_document(
        text: str, title: str | None = None, source_url: str | None = None
    ) -> dict[str, Any]:
        """Store immutable UTF-8 text and return its ID, hash, and source metadata."""
        if not text:
            raise ValueError("text must not be empty")
        try:
            return store.store(text, title=title, source_url=source_url)
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="kev_fetch_document", structured_output=True)
    async def fetch_and_store(url: str) -> dict[str, Any]:
        """Fetch bounded public HTML or plain text, then retain it under a document ID."""
        try:
            fetched = await fetch_document(
                url, max_bytes=settings.max_document_bytes, timeout_seconds=20
            )
            return store.store(**fetched)
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="kev_read_document", structured_output=True)
    def read_document(
        document_id: str, start_line: int | None = None, end_line: int | None = None
    ) -> dict[str, Any]:
        """Read full or selected lines with explicit full or partial coverage metadata."""
        try:
            return store.read(
                document_id, start_line=start_line, end_line=end_line, max_chars=16000
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="kev_evaluate_document", structured_output=True)
    async def evaluate_document(
        document_id: str,
        questions: Questions,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        """Evaluate typed questions; probabilities describe confidence, not accuracy.

        Coverage marks whether the full document or a partial line selection was evaluated.
        """
        try:
            selected = store.select(document_id, start_line=start_line, end_line=end_line)
            result = await backend.evaluate(selected["text"], validate_questions(questions))
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        result = dict(result)
        result["document"] = selected["document"]
        result["coverage"] = selected["coverage"]
        result.setdefault("runtime", {})
        return result

    @server.tool(name="kev_capabilities", structured_output=True)
    async def capabilities() -> dict[str, Any]:
        """Report strict backend limits, supported question types, and loaded model identity."""
        try:
            return await backend.capabilities()
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    return server


class _BearerAuthMiddleware:
    """Reject every HTTP request without the configured bearer token."""

    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        request_headers = {key.lower(): value for key, value in scope.get("headers", [])}
        expected = b"Bearer " + self.token
        if not hmac.compare_digest(request_headers.get(b"authorization", b""), expected):
            body = b'{"error":"unauthorized"}'
            response_headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ]
            await send({"type": "http.response.start", "status": 401, "headers": response_headers})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _http_app(settings: Settings, server: MCPServer) -> Any:
    if not _is_loopback(settings.host) and not settings.token:
        raise ValueError("KEV_MCP_TOKEN is required for non-loopback HTTP")
    if settings.host in {"0.0.0.0", "::"} and not settings.allowed_hosts:
        raise ValueError("KEV_MCP_ALLOWED_HOSTS is required when binding to all interfaces")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(
            settings.allowed_hosts or (f"{settings.host}:{settings.port}", settings.host)
        ),
        allowed_origins=list(
            settings.allowed_origins or (f"http://{settings.host}:{settings.port}",)
        ),
    )
    app: Any = server.streamable_http_app(
        host=settings.host,
        max_request_body_size=settings.max_request_body_bytes,
        transport_security=security,
    )
    if settings.token:
        app = _BearerAuthMiddleware(app, settings.token)
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Kev MCP bridge")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    has_override = args.host is not None or args.port is not None
    settings = Settings.from_env(transport="stdio" if has_override else args.transport)
    if has_override:
        if args.port is not None and not 1 <= args.port <= 65535:
            raise ValueError("--port must be a valid TCP port")
        values = {
            **settings.__dict__,
            "host": args.host or settings.host,
            "port": args.port or settings.port,
        }
        if (
            args.transport == "streamable-http"
            and not _is_loopback(values["host"])
            and not settings.token
        ):
            raise ValueError("KEV_MCP_TOKEN is required for non-loopback HTTP")
        settings = Settings(**values)
    server = create_server(settings)
    logging.basicConfig(level=logging.INFO, stream=__import__("sys").stderr)
    if args.transport == "stdio":
        server.run("stdio")
        return
    import uvicorn

    uvicorn.run(
        _http_app(settings, server), host=settings.host, port=settings.port, log_level="info"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
