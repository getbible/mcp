from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from getbible_mcp.cache import MAX_RETENTION_SECONDS, cache_advice
from getbible_mcp.models import SourceInfo

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def source(**headers: str) -> SourceInfo:
    return SourceInfo(
        url="https://api.test/v3/kjv/1/1.json", fetched_at=NOW, api_version="v3", headers=headers
    )


def test_static_retention_never_exceeds_thirty_days() -> None:
    advice = cache_advice(source(**{"cache-control": "public, max-age=999999999999999"}))
    assert advice.max_retention_seconds == MAX_RETENTION_SECONDS
    assert advice.remaining_ttl_seconds == MAX_RETENTION_SECONDS
    assert advice.expires_at == NOW + timedelta(days=30)
    assert advice.hash_validation_required is True
    assert "unchanged hash" in advice.policy and "does not renew" in advice.policy


def test_shorter_max_age_and_age_reduce_remaining_lifetime() -> None:
    advice = cache_advice(source(**{"cache-control": "max-age=120", "age": "40"}))
    assert advice.remaining_ttl_seconds == 80
    assert advice.expires_at == NOW + timedelta(seconds=80)


def test_apparent_age_uses_date_when_older_than_age_header() -> None:
    advice = cache_advice(
        source(
            **{
                "cache-control": "max-age=120",
                "age": "20",
                "date": format_datetime(NOW - timedelta(seconds=50)),
            }
        )
    )
    assert advice.remaining_ttl_seconds == 70


def test_expires_deadline_and_age_are_respected() -> None:
    advice = cache_advice(
        source(
            **{
                "cache-control": "max-age=1000",
                "date": format_datetime(NOW - timedelta(seconds=20)),
                "expires": format_datetime(NOW + timedelta(seconds=40)),
                "age": "30",
            }
        )
    )
    assert advice.remaining_ttl_seconds == 30


def test_original_upstream_date_bounds_thirty_day_retention() -> None:
    advice = cache_advice(source(**{"date": format_datetime(NOW - timedelta(days=29))}))
    assert advice.remaining_ttl_seconds == 24 * 60 * 60


@pytest.mark.parametrize(
    "directive",
    [
        "no-store",
        "NO-CACHE",
        "private",
        'private="authorization"',
        "max-age=0",
        "max-age=-1",
        "max-age=invalid",
    ],
)
def test_forbidden_or_stale_responses_cannot_be_cached(directive: str) -> None:
    advice = cache_advice(source(**{"cache-control": directive}))
    assert advice.cacheable is False
    assert advice.recommended is False
    assert advice.remaining_ttl_seconds == 0


@pytest.mark.parametrize(
    "headers",
    [
        {"age": "-1"},
        {"age": "bad"},
        {"age": "9" * 5000},
        {"expires": "bad"},
        {"date": "bad"},
    ],
)
def test_invalid_or_expired_http_age_cannot_extend_retention(headers: dict[str, str]) -> None:
    advice = cache_advice(source(**headers))
    assert advice.cacheable is False
    assert advice.remaining_ttl_seconds == 0


def test_contradictory_freshness_uses_shortest_directive() -> None:
    advice = cache_advice(source(**{"cache-control": 'max-age=200, s-maxage=60, max-age="100"'}))
    assert advice.remaining_ttl_seconds == 60


def test_leading_zeroes_cannot_extend_short_lifetime() -> None:
    advice = cache_advice(
        source(**{"cache-control": "max-age=00000000000000000000000000000000001"})
    )
    assert advice.remaining_ttl_seconds == 1


@pytest.mark.parametrize("service", ["query", "search"])
def test_runtime_get_cache_is_discouraged_with_explicit_retention_cap(service: str) -> None:
    item = source(**{"cache-control": "max-age=300"})
    item.service = service  # type: ignore[assignment]
    advice = cache_advice(item)
    assert advice.cacheable is True
    assert advice.recommended is False
    assert advice.hash_validation_required is False
    assert advice.remaining_ttl_seconds == 300


@pytest.mark.parametrize("method,status", [("POST", 200), ("GET", 304), ("GET", 404), ("GET", 503)])
def test_post_and_non_successes_are_not_cacheable(method: str, status: int) -> None:
    item = source(**{"cache-control": "max-age=300"})
    item.status_code = status
    advice = cache_advice(item, method)
    assert advice.cacheable is False
    assert advice.remaining_ttl_seconds == 0
