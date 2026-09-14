"""Bounded, HTTP-aware consumer cache advice without any response storage."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from getbible_mcp.models import CacheAdvice, SourceInfo

MAX_RETENTION_SECONDS = 30 * 24 * 60 * 60
STATIC_CACHE_POLICY = (
    "Cache for at most 30 days from the original upstream response, honoring any shorter HTTP "
    "freshness lifetime and Age. Preserve the exact version-specific hash and invalidate the "
    "scope and its descendants when it changes. An unchanged hash or a 304 response does not "
    "renew the 30-day retention limit: fetch and replace the content by that deadline. "
    "Bible SHA-1 version tokens and study-resource SHA-256 manifests have distinct contracts. "
    "A before/after hash check detects a rotation during a read; it does not verify the bytes "
    "against a cryptographic checksum. The MCP itself does not cache responses."
)
RUNTIME_CACHE_POLICY = (
    "Use query and search results directly; caching is not recommended. The MCP does not cache "
    "these results or infer chapter hashes. If your integration caches an eligible GET result, "
    "honor its HTTP headers and never retain it for longer than 30 days from the original "
    "upstream response. POST, no-store, no-cache and private responses must not be cached. "
    "Preserve any native query.sha and query.cache metadata without inventing hash endpoints."
)


def _http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def cache_advice(source: SourceInfo, method: str = "GET") -> CacheAdvice:
    """Compute a conservative lifetime, including apparent age and explicit HTTP freshness.

    The policy bounds retention from the upstream response's age; callers must additionally keep
    the original acquisition deadline when revalidating data they already hold.
    """

    runtime = source.service in {"query", "search"}
    policy = RUNTIME_CACHE_POLICY if runtime else STATIC_CACHE_POLICY
    now = source.fetched_at
    headers = source.headers
    control = headers.get("cache-control", "")
    # Multiple directives are retained so contradictory max-age values cannot extend retention.
    directives: dict[str, list[str | None]] = {}
    for item in control.split(","):
        name, separator, value = item.strip().partition("=")
        if name:
            directives.setdefault(name.casefold(), []).append(
                value.strip().strip('"') if separator else None
            )
    allowed = (
        method.upper() == "GET"
        and 200 <= source.status_code < 300
        and not {"no-store", "no-cache", "private"}.intersection(directives)
    )
    lifetime = MAX_RETENTION_SECONDS
    for name in ("max-age", "s-maxage"):
        for directive_value in directives.get(name, []):
            if directive_value is None or not re.fullmatch(r"[0-9]+", directive_value):
                allowed = False
            else:
                # Avoid converting attacker-controlled arbitrarily long decimal strings.
                numeric = directive_value.lstrip("0") or "0"
                parsed = MAX_RETENTION_SECONDS if len(numeric) > 10 else int(numeric)
                lifetime = min(lifetime, parsed)

    date = _http_date(headers.get("date"))
    if "date" in headers and date is None:
        allowed = False
    age = max(0.0, (now - date).total_seconds()) if date else 0.0
    age_header = headers.get("age")
    if age_header is not None:
        if not re.fullmatch(r"[0-9]+", age_header.strip()):
            allowed = False
        else:
            value = age_header.strip().lstrip("0") or "0"
            age = max(age, MAX_RETENTION_SECONDS if len(value) > 10 else int(value))

    expires_header = headers.get("expires")
    expires = _http_date(expires_header)
    if expires_header is not None:
        if expires is None:
            allowed = False
        else:
            # Use the stricter explicit deadline even if max-age is also supplied.
            lifetime = min(lifetime, max(0, int((expires - (date or now)).total_seconds())))

    remaining = max(0, int(lifetime - age)) if allowed else 0
    allowed = allowed and remaining > 0
    return CacheAdvice(
        cacheable=allowed,
        recommended=allowed and not runtime,
        remaining_ttl_seconds=remaining,
        expires_at=now + timedelta(seconds=remaining),
        hash_validation_required=allowed and not runtime,
        policy=policy,
    )
