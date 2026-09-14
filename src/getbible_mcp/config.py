"""Environment-backed configuration with production-safe defaults."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from getbible_mcp import __version__


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
    if not math.isfinite(value) or value <= 0:
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
    """Explicit, operator-configured upstreams for every supported API contract.

    Every upstream version has an explicit configuration key. Tool callers cannot
    supply upstream URLs; deployments may configure their own trusted GetBible mirrors here.
    """

    api_v2_base: str = "https://api.getbible.net/v2"
    query_v2_base: str = "https://query.getbible.net/v2"
    api_v3_base: str = "https://api.getbible.net/v3"
    query_v3_base: str = "https://query.getbible.net/v3"
    search_v2_base: str = "https://search.getbible.net/v2"
    search_v3_base: str = "https://search.getbible.net/v3"
    dictionaries_base: str = "https://dictionaries.getbible.net/v1"
    commentaries_base: str = "https://commentaries.getbible.net/v1"
    bookmarks_base: str = "https://bookmarks.getbible.net/v1"
    public_base: str = "https://mcp.getbible.net"
    bind_host: str = "127.0.0.1"
    bind_port: int = 3100
    workers: int = 2
    request_timeout_seconds: float = 20.0
    max_response_bytes: int = 32 * 1024 * 1024
    max_parallel_hash_checks: int = 10
    user_agent: str = f"getbible-mcp/{__version__} (+https://getBible.net)"
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

    def __post_init__(self) -> None:
        for service, versions in (
            ("api", ("v2", "v3")),
            ("query", ("v2", "v3")),
            ("search", ("v2", "v3")),
            ("dictionaries", ("v1",)),
            ("commentaries", ("v1",)),
            ("bookmarks", ("v1",)),
        ):
            for version in versions:
                base = self.service_base(service, version)
                parsed = urlsplit(base)
                _ = parsed.port  # Validate malformed or out-of-range operator-configured ports.
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                    or not parsed.path.endswith(f"/{version}")
                ):
                    raise ValueError(
                        f"{service} {version} base must be an HTTP(S) URL ending in /{version} "
                        "without credentials, a query or fragment"
                    )
        for name in ("request_timeout_seconds", "max_response_bytes", "max_parallel_hash_checks"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")

    def service_base(self, service: str, version: str) -> str:
        names = {
            ("api", "v2"): "api_v2_base",
            ("api", "v3"): "api_v3_base",
            ("query", "v2"): "query_v2_base",
            ("query", "v3"): "query_v3_base",
            ("search", "v2"): "search_v2_base",
            ("search", "v3"): "search_v3_base",
            ("dictionaries", "v1"): "dictionaries_base",
            ("commentaries", "v1"): "commentaries_base",
            ("bookmarks", "v1"): "bookmarks_base",
        }
        try:
            attribute = names[(service, version)]
        except KeyError as exc:
            raise ValueError(f"Unsupported GetBible service/version: {service}/{version}") from exc
        return str(getattr(self, attribute)).rstrip("/")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_v2_base=os.getenv("GETBIBLE_API_V2_BASE", cls.api_v2_base).rstrip("/"),
            query_v2_base=os.getenv("GETBIBLE_QUERY_V2_BASE", cls.query_v2_base).rstrip("/"),
            api_v3_base=os.getenv("GETBIBLE_API_V3_BASE", cls.api_v3_base).rstrip("/"),
            query_v3_base=os.getenv("GETBIBLE_QUERY_V3_BASE", cls.query_v3_base).rstrip("/"),
            search_v2_base=os.getenv("GETBIBLE_SEARCH_V2_BASE", cls.search_v2_base).rstrip("/"),
            search_v3_base=os.getenv("GETBIBLE_SEARCH_V3_BASE", cls.search_v3_base).rstrip("/"),
            dictionaries_base=os.getenv("GETBIBLE_DICTIONARIES_BASE", cls.dictionaries_base).rstrip(
                "/"
            ),
            commentaries_base=os.getenv("GETBIBLE_COMMENTARIES_BASE", cls.commentaries_base).rstrip(
                "/"
            ),
            bookmarks_base=os.getenv("GETBIBLE_BOOKMARKS_BASE", cls.bookmarks_base).rstrip("/"),
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
