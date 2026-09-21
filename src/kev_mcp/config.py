"""Environment configuration for the Kev MCP bridge."""

from __future__ import annotations

import ipaddress
import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"{name} must be greater than zero")
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if value <= 0 or value > 65535:
        raise ValueError(f"{name} must be a valid TCP port")
    return value


def _positive_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() in {"localhost", "localhost.localdomain"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    api_key: str
    db_path: Path
    timeout: float = 120.0
    host: str = "127.0.0.1"
    port: int = 8000
    token: str | None = None
    max_document_bytes: int = 2_000_000
    max_request_body_bytes: int = 4_194_304
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, *, transport: str = "stdio") -> "Settings":
        base_url = os.getenv("KEV_BASE_URL", "http://127.0.0.1:8009").rstrip("/")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("KEV_BASE_URL must be an HTTP(S) URL")
        base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
        host = os.getenv("KEV_MCP_HOST", "127.0.0.1")
        port = _env_int("KEV_MCP_PORT", 8000)
        token = os.getenv("KEV_MCP_TOKEN")
        if transport == "streamable-http" and not _is_loopback(host) and not token:
            raise ValueError("KEV_MCP_TOKEN is required for non-loopback HTTP")
        allowed_hosts = tuple(
            x.strip() for x in os.getenv("KEV_MCP_ALLOWED_HOSTS", "").split(",") if x.strip()
        )
        allowed_origins = tuple(
            x.strip() for x in os.getenv("KEV_MCP_ALLOWED_ORIGINS", "").split(",") if x.strip()
        )
        if transport == "streamable-http" and host in {"0.0.0.0", "::"} and not allowed_hosts:
            raise ValueError("KEV_MCP_ALLOWED_HOSTS is required when binding to all interfaces")
        default_db = Path.home() / ".local/share/kev-mcp/store.sqlite3"
        db_path = Path(os.getenv("KEV_MCP_DB", str(default_db))).expanduser()
        return cls(
            base_url=base_url,
            model=os.getenv("KEV_MODEL", "kev-latest"),
            api_key=os.getenv("KEV_API_KEY", "local"),
            db_path=db_path,
            timeout=_env_float("KEV_TIMEOUT", 120.0),
            host=host,
            port=port,
            token=token,
            max_document_bytes=_positive_env_int("KEV_MAX_DOCUMENT_BYTES", 2_000_000),
            max_request_body_bytes=_positive_env_int("KEV_MAX_REQUEST_BODY_BYTES", 4_194_304),
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )
