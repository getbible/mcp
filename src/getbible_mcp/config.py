"""Environment-backed configuration with production-safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values:
        raise ValueError(f"{name} must contain at least one value")
    return values


@dataclass(frozen=True)
class Settings:
    """GetBible MCP settings.

    API bases are deliberately pinned to V2. A different GetBible API version must use a separate
    MCP implementation and public endpoint.
    """

    api_base: str = "https://api.getbible.net/v2"
    query_base: str = "https://query.getbible.net/v2"
    public_base: str = "https://mcp.getbible.net"
    bind_host: str = "127.0.0.1"
    bind_port: int = 3100
    workers: int = 2
    request_timeout_seconds: float = 20.0
    max_response_bytes: int = 32 * 1024 * 1024
    max_parallel_hash_checks: int = 10
    user_agent: str = "getbible-mcp/1.0 (+https://getbible.life)"
    allowed_hosts: tuple[str, ...] = (
        "mcp.getbible.net",
        "mcp.getbible.net:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "testserver",
    )
    allowed_origins: tuple[str, ...] = (
        "https://mcp.getbible.net",
        "http://127.0.0.1:*",
        "http://localhost:*",
    )

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_base=os.getenv("GETBIBLE_API_BASE", cls.api_base).rstrip("/"),
            query_base=os.getenv("GETBIBLE_QUERY_BASE", cls.query_base).rstrip("/"),
            public_base=os.getenv("GETBIBLE_MCP_PUBLIC_BASE", cls.public_base).rstrip("/"),
            bind_host=os.getenv("GETBIBLE_MCP_BIND_HOST", cls.bind_host),
            bind_port=_positive_int("GETBIBLE_MCP_BIND_PORT", cls.bind_port),
            workers=_positive_int("GETBIBLE_MCP_WORKERS", cls.workers),
            request_timeout_seconds=_positive_float(
                "GETBIBLE_MCP_REQUEST_TIMEOUT", cls.request_timeout_seconds
            ),
            max_response_bytes=_positive_int(
                "GETBIBLE_MCP_MAX_RESPONSE_BYTES", cls.max_response_bytes
            ),
            max_parallel_hash_checks=_positive_int(
                "GETBIBLE_MCP_MAX_PARALLEL_HASH_CHECKS", cls.max_parallel_hash_checks
            ),
            user_agent=os.getenv("GETBIBLE_MCP_USER_AGENT", cls.user_agent),
            allowed_hosts=_csv("GETBIBLE_MCP_ALLOWED_HOSTS", cls.allowed_hosts),
            allowed_origins=_csv("GETBIBLE_MCP_ALLOWED_ORIGINS", cls.allowed_origins),
        )

