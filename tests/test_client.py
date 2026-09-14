from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from getbible_mcp.client import (
    ContentChangedDuringReadError,
    GetBibleClient,
    InvalidRequestError,
    UpstreamError,
)
from getbible_mcp.config import Settings
from getbible_mcp.models import ScopeSpec

SHA_A = "a" * 40
SHA_B = "b" * 40


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], **settings: Any
) -> GetBibleClient:
    configured: dict[str, Any] = {
        "api_base": "https://api.test/v2",
        "api_v3_base": "https://api.test/v3",
        "query_base": "https://query.test/v2",
        "query_v3_base": "https://query.test/v3",
        "search_base": "https://search.test/v2",
        "search_v3_base": "https://search.test/v3",
        "dictionaries_base": "https://dictionaries.test/v1",
        "commentaries_base": "https://commentaries.test/v1",
        "bookmarks_base": "https://bookmarks.test/v1",
        "max_response_bytes": 1024 * 1024,
        **settings,
    }
    return GetBibleClient(
        settings=Settings(**configured),
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ),
    )


@pytest.mark.parametrize("version", ["v2", "v3"])
async def test_scripture_checks_rotation_before_and_after_native_json(version: str) -> None:
    calls: list[str] = []
    native = {
        "book": "Genesis",
        "chapter": 1,
        "editorial": [{"type": "heading", "text": "Creation"}],
        "verses": [{"text": "In the beginning", "tokens": [{"lemma": {"strong": ["H7225"]}}]}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith(".sha"):
            return httpx.Response(200, text=f"{SHA_A}\n")
        return httpx.Response(200, json=native)

    client = make_client(handler)
    result = await client.get_scripture(
        ScopeSpec.model_validate(
            {
                "kind": "chapter",
                "translation": "kjv",
                "book": 1,
                "chapter": 1,
                "api_version": version,
            }
        )
    )
    assert result.hash == SHA_A
    assert result.data == native
    assert result.source.api_version == version
    assert result.consistency_checked is True
    assert result.consistency_retries == 0
    assert calls == [
        f"/{version}/kjv/1/1.sha",
        f"/{version}/kjv/1/1.json",
        f"/{version}/kjv/1/1.sha",
    ]
    assert "does not verify" in result.cache_policy


async def test_scripture_retries_one_rotation() -> None:
    sha_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sha_calls
        if request.url.path.endswith(".sha"):
            sha_calls += 1
            return httpx.Response(200, text=[SHA_A, SHA_B, SHA_B, SHA_B][sha_calls - 1])
        return httpx.Response(200, json={"version": sha_calls})

    result = await make_client(handler).get_scripture(
        ScopeSpec(kind="translation", translation="kjv")
    )
    assert result.hash == SHA_B
    assert result.consistency_retries == 1
    assert result.data == {"version": 3}


async def test_repeated_rotation_fails_without_claiming_consistency() -> None:
    sha_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sha_calls
        if request.url.path.endswith(".sha"):
            sha_calls += 1
            return httpx.Response(200, text=SHA_A if sha_calls % 2 else SHA_B)
        return httpx.Response(200, json={})

    with pytest.raises(ContentChangedDuringReadError):
        await make_client(handler).get_scripture(ScopeSpec(kind="translation", translation="kjv"))
    assert sha_calls == 4


@pytest.mark.parametrize("version", ["v2", "v3"])
async def test_query_uses_only_runtime_and_preserves_native_results(version: str) -> None:
    calls: list[httpx.Request] = []
    native = {"kjv_43_3": {"verses": [{"verse": 16, "text": "For God", "extra": {"x": 1}}]}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=native, headers={"cache-control": "max-age=120"})

    result = await make_client(handler).query_verses("kjv", "John 3:16; 1John3:16-19", version)
    assert len(calls) == 1
    assert calls[0].url.host == "query.test"
    assert calls[0].url.path.startswith(f"/{version}/kjv/")
    assert result.data == native
    assert result.chapter_hashes == []
    assert result.unresolved_references == []
    assert result.cacheable is False
    assert result.consistency_checked is False
    assert result.consistency_retries == 0
    assert result.cache is not None and result.cache.recommended is False
    assert result.cache.remaining_ttl_seconds <= 120


@pytest.mark.parametrize(
    ("service", "version", "operation", "expected"),
    [
        ("api", "v2", "listTranslations", "/v2/translations.json"),
        ("api", "v3", "getTranslations", "/v3/translations.json"),
        ("query", "v2", "openapi", "/v2/openapi.json"),
        ("query", "v3", "openapi", "/v3/openapi.json"),
        ("search", "v2", "openapi", "/v2/openapi.json"),
        ("search", "v3", "openapi", "/v3/openapi.json"),
        ("dictionaries", "v1", "listDictionaries", "/v1/dictionaries.json"),
        ("commentaries", "v1", "listCommentaries", "/v1/commentaries.json"),
        ("bookmarks", "v1", "getIndex", "/v1/index.json"),
    ],
)
async def test_all_contract_versions_use_their_configured_destination(
    service: str, version: str, operation: str, expected: str
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"native": {"anything": [1, None, "text"]}})

    result = await make_client(handler).call_api_operation(service, version, operation)
    assert len(calls) == 1
    assert calls[0].url.host == f"{service}.test"
    assert calls[0].url.path == expected
    assert result.source.service == service
    assert result.source.api_version == version
    assert result.data == {"native": {"anything": [1, None, "text"]}}


async def test_search_repeats_filters_and_preserves_response_metadata() -> None:
    calls: list[httpx.Request] = []
    native = {
        "query": {"sha": "native", "cache": {"stale": False, "checked_at": 123.5}},
        "results": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=native)

    result = await make_client(handler).call_api_operation(
        "search",
        "v3",
        "search",
        {
            "translation": "kjv",
            "search": "faith & hope",
            "book": [1, "John"],
            "exclude": ["fear", "hate"],
            "case_sensitive": False,
        },
    )
    assert calls[0].url.params.get_list("book") == ["1", "John"]
    assert calls[0].url.params.get_list("exclude") == ["fear", "hate"]
    assert calls[0].url.params["case_sensitive"] == "false"
    assert result.data == native
    assert result.cache.recommended is False


async def test_search_post_is_read_only_and_cannot_be_cached() -> None:
    calls: list[httpx.Request] = []
    body = {"q": "faith hope", "words": "any", "book": [1, "John"], "limit": 25}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, json={"query": {"kind": "search"}}, headers={"cache-control": "max-age=900"}
        )

    result = await make_client(handler).call_api_operation(
        "search", "v3", "searchTranslationPost", {"translation": "kjv"}, body
    )
    assert calls[0].method == "POST"
    assert json.loads(calls[0].content) == body
    assert result.cache.cacheable is False
    assert result.cache.remaining_ttl_seconds == 0


async def test_text_checksum_and_tsv_operations_preserve_plain_text() -> None:
    text = "kjv\tKing James Version\n"
    result = await make_client(lambda _: httpx.Response(200, text=text)).call_api_operation(
        "api", "v2", "listTranslationsText"
    )
    assert result.data == text


async def test_upstream_errors_preserve_status_body_and_safe_headers() -> None:
    native = {"error": "rate limit exceeded", "details": {"retry": True}}
    client = make_client(
        lambda _: httpx.Response(
            429, json=native, headers={"retry-after": "12", "set-cookie": "secret=1"}
        )
    )
    with pytest.raises(UpstreamError, match="HTTP 429") as error:
        await client.list_translations()
    assert error.value.status_code == 429
    assert error.value.body == native
    assert error.value.result is not None
    assert error.value.result.source.headers["retry-after"] == "12"
    assert "set-cookie" not in error.value.result.source.headers
    assert error.value.to_dict()["result"]["data"] == native
    assert error.value.result.cache.cacheable is False


async def test_documented_redirect_is_returned_and_never_followed() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            301, text="redirect", headers={"location": "https://external.test/private"}
        )

    result = await make_client(handler).call_api_operation(
        "query", "v3", "redirectReference", {"reference": "John3:16"}
    )
    assert len(calls) == 1
    assert calls[0].url.path == "/John3:16"
    assert result.source.status_code == 301
    assert result.source.headers["location"] == "https://external.test/private"
    assert result.data == "redirect"
    assert result.cache.cacheable is False


async def test_undocumented_redirect_is_a_structured_error() -> None:
    client = make_client(
        lambda _: httpx.Response(302, headers={"location": "https://external.test/"})
    )
    with pytest.raises(UpstreamError, match="HTTP 302"):
        await client.list_translations()


async def test_documented_304_has_no_body_and_does_not_renew_retention() -> None:
    result = await make_client(lambda _: httpx.Response(304)).call_api_operation(
        "search", "v3", "search", {"translation": "kjv", "search": "faith"}
    )
    assert result.data is None
    assert result.cache.cacheable is False
    assert result.cache.remaining_ttl_seconds == 0


@pytest.mark.parametrize(
    "body", [b"not-json", b'{"value": NaN}', b'{"value": Infinity}', b'{"value": 1e400}']
)
async def test_malformed_json_is_a_structured_error(body: bytes) -> None:
    client = make_client(
        lambda _: httpx.Response(200, content=body, headers={"content-type": "application/json"})
    )
    with pytest.raises(UpstreamError, match="invalid JSON") as error:
        await client.list_translations()
    assert error.value.result is not None
    assert error.value.result.cache.cacheable is False


async def test_successful_html_instead_of_json_is_rejected() -> None:
    client = make_client(
        lambda _: httpx.Response(
            200, text="<html>Proxy error</html>", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(UpstreamError, match="Content-Type"):
        await client.list_translations()


async def test_rejects_translation_path_injection_without_network() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid requests must not reach the upstream")

    with pytest.raises(InvalidRequestError):
        await make_client(handler).list_books("../../internal")


async def test_contract_rejects_unknown_operation_and_invalid_scope_before_network() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid requests must not reach the upstream")

    client = make_client(handler)
    with pytest.raises(InvalidRequestError):
        await client.call_api_operation("api", "v2", "deleteTranslation")
    with pytest.raises(InvalidRequestError):
        await client.list_chapters("kjv", 1000000, "v2")
    with pytest.raises(InvalidRequestError):
        await client.query_verses("kjv", "x" * 513)


async def test_v3_extended_book_ids_are_supported() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, text=SHA_A)

    scope = ScopeSpec(
        kind="chapter", translation="kjv", book=1000000, chapter=401, api_version="v3"
    )
    result = await make_client(handler).get_hash(scope)
    assert result.hash == SHA_A
    assert calls == ["/v3/kjv/1000000/401.sha"]


async def test_rejects_invalid_sha() -> None:
    client = make_client(lambda _: httpx.Response(200, text="not-a-sha"))
    with pytest.raises(UpstreamError, match="invalid SHA"):
        await client.get_hash(ScopeSpec(kind="translation", translation="kjv"))


@pytest.mark.parametrize("length", ["2097152", "-1", "wrong", "9" * 5000])
async def test_rejects_invalid_or_oversize_declared_response(length: str) -> None:
    client = make_client(
        lambda _: httpx.Response(200, content=b"{}", headers={"content-length": length})
    )
    with pytest.raises(UpstreamError):
        await client.list_translations()


class ResponseChunks(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"["
        yield b" " * 500
        yield b"]"


async def test_streamed_response_limit_is_enforced_without_content_length() -> None:
    client = make_client(
        lambda _: httpx.Response(200, stream=ResponseChunks()), max_response_bytes=100
    )
    with pytest.raises(UpstreamError, match="size limit"):
        await client.list_translations()


async def test_total_request_timeout_bounds_slow_upstreams() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    client = GetBibleClient(
        Settings(request_timeout_seconds=0.01),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamError, match="Unable to reach"):
        await client.list_translations()


def test_settings_retain_v2_environment_names_and_add_versioned_bases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETBIBLE_API_BASE", "https://old.test/mirror/v2/")
    monkeypatch.setenv("GETBIBLE_API_V3_BASE", "https://new.test/v3/")
    settings = Settings.from_env()
    assert settings.service_base("api", "v2") == "https://old.test/mirror/v2"
    assert settings.service_base("api", "v3") == "https://new.test/v3"


@pytest.mark.parametrize(
    "base",
    [
        "file:///v2",
        "https://user:pass@api.test/v2",
        "https://api.test/v3",
        "https://api.test/v2?x=1",
    ],
)
def test_settings_reject_ambiguous_upstream_bases(base: str) -> None:
    with pytest.raises(ValueError):
        Settings(api_base=base)
