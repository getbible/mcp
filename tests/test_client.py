from __future__ import annotations

import json

import httpx
import pytest

from getbible_mcp.client import GetBibleClient, InvalidRequestError, UpstreamError
from getbible_mcp.config import Settings
from getbible_mcp.models import ScopeSpec

SHA_A = "a" * 40
SHA_B = "b" * 40


def make_client(handler: httpx.MockTransport) -> GetBibleClient:
    settings = Settings(
        api_base="https://api.test/v2",
        query_base="https://query.test/v2",
        max_response_bytes=1024 * 1024,
    )
    return GetBibleClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=handler),
    )


@pytest.mark.asyncio
async def test_get_scripture_checks_hash_before_and_after_json() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v2/kjv/1/1.sha":
            return httpx.Response(200, text=f"{SHA_A}\n")
        if request.url.path == "/v2/kjv/1/1.json":
            return httpx.Response(200, json={"book": "Genesis", "chapter": 1})
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler))
    result = await client.get_scripture(
        ScopeSpec(kind="chapter", translation="kjv", book=1, chapter=1)
    )

    assert result.hash == SHA_A
    assert result.data["book"] == "Genesis"
    assert result.consistency_checked is True
    assert result.consistency_retries == 0
    assert calls == ["/v2/kjv/1/1.sha", "/v2/kjv/1/1.json", "/v2/kjv/1/1.sha"]


@pytest.mark.asyncio
async def test_get_scripture_retries_one_mid_read_change() -> None:
    sha_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sha_calls
        if request.url.path.endswith(".sha"):
            sha_calls += 1
            values = [SHA_A, SHA_B, SHA_B, SHA_B]
            return httpx.Response(200, text=values[sha_calls - 1])
        return httpx.Response(200, json={"version": sha_calls})

    client = make_client(httpx.MockTransport(handler))
    result = await client.get_scripture(ScopeSpec(kind="translation", translation="kjv"))

    assert result.hash == SHA_B
    assert result.consistency_retries == 1
    assert result.data == {"version": 3}


@pytest.mark.asyncio
async def test_query_returns_every_participating_chapter_hash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "query.test":
            return httpx.Response(200, json={"verses": [{"text": "For God so loved..."}]})
        if path == "/v2/kjv/books.json":
            return httpx.Response(
                200,
                json={
                    "books": [
                        {"nr": 43, "name": "John"},
                        {"nr": 62, "name": "1 John"},
                    ]
                },
            )
        if path in {"/v2/kjv/43/3.sha", "/v2/kjv/62/3.sha"}:
            return httpx.Response(200, text=SHA_A if "/43/" in path else SHA_B)
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler))
    result = await client.query_verses("kjv", "John 3:16; 1John3:16-19")

    assert result.cacheable is True
    assert result.consistency_checked is True
    assert result.unresolved_references == []
    assert {(item.book, item.chapter) for item in result.chapter_hashes} == {(43, 3), (62, 3)}


@pytest.mark.asyncio
async def test_query_supports_numeric_book_reference_with_required_space() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "query.test":
            return httpx.Response(200, json={"verses": []})
        if request.url.path == "/v2/kjv/books.json":
            return httpx.Response(200, json={"books": [{"nr": 62, "name": "1 John"}]})
        if request.url.path == "/v2/kjv/62/3.sha":
            return httpx.Response(200, text=SHA_A)
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler))
    result = await client.query_verses("kjv", "62 3:16-19")

    assert result.cacheable is True
    assert [(item.book, item.chapter) for item in result.chapter_hashes] == [(62, 3)]


@pytest.mark.asyncio
async def test_query_retries_when_participating_chapter_changes() -> None:
    sha_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sha_calls
        if request.url.host == "query.test":
            return httpx.Response(200, json={"sha_calls_at_query": sha_calls})
        if request.url.path == "/v2/kjv/books.json":
            return httpx.Response(200, json={"books": [{"nr": 43, "name": "John"}]})
        if request.url.path == "/v2/kjv/43/3.sha":
            sha_calls += 1
            return httpx.Response(200, text=[SHA_A, SHA_B, SHA_B, SHA_B][sha_calls - 1])
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler))
    result = await client.query_verses("kjv", "John 3:16")

    assert result.consistency_retries == 1
    assert result.chapter_hashes[0].hash == SHA_B
    assert result.data == {"sha_calls_at_query": 3}


@pytest.mark.asyncio
async def test_query_marks_unknown_book_non_cacheable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "query.test":
            return httpx.Response(200, json={"verses": []})
        if request.url.path == "/v2/kjv/books.json":
            return httpx.Response(200, json={"books": [{"nr": 43, "name": "John"}]})
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler))
    result = await client.query_verses("kjv", "Unknown 1:1")

    assert result.cacheable is False
    assert result.unresolved_references == ["Unknown 1:1"]
    assert result.chapter_hashes == []


@pytest.mark.asyncio
async def test_rejects_translation_path_injection() -> None:
    client = make_client(httpx.MockTransport(lambda _: httpx.Response(500)))
    with pytest.raises(InvalidRequestError):
        await client.list_books("../../internal")


@pytest.mark.asyncio
async def test_rejects_invalid_sha() -> None:
    client = make_client(httpx.MockTransport(lambda _: httpx.Response(200, text="not-a-sha")))
    with pytest.raises(UpstreamError, match="invalid SHA"):
        await client.get_hash(ScopeSpec(kind="translation", translation="kjv"))


@pytest.mark.asyncio
async def test_rejects_oversize_declared_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps({"ok": True}),
            headers={"content-length": str(2 * 1024 * 1024)},
        )

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(UpstreamError, match="size limit"):
        await client.list_translations()
