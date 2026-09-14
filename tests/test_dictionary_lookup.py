"""Bounded dictionary lookup preserves native records and upstream failures."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator
from test_client import make_client
from test_server_http import http_session, structured_result

from getbible_mcp.client import InvalidRequestError, UpstreamError


def dictionary_index() -> dict[str, Any]:
    return {
        "schema": "getbible-dictionary-index-v1",
        "dictionary": "strongsgreek",
        "language": "el",
        "name": "Fixture lexicon",
        "entry_url_template": "{entry}.json",
        "entry_count": 4,
        "unique_key_count": 3,
        "entries": [
            {"id": "G3004", "key": "λέγω", "search": "λεγω"},
            {"id": "G3056", "key": "λόγος", "search": "λογος", "aliases": ["logos"]},
            {"id": "G3056--2", "key": "λόγος", "search": "λογος", "occurrence": 2},
            {"id": "fixture", "key": "Straße", "search": "strasse", "aliases": ["Road"]},
        ],
    }


async def test_unicode_repeated_keys_pagination_and_fresh_upstream_fetches() -> None:
    native = dictionary_index()
    original = deepcopy(native)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=native, headers={"cache-control": "max-age=60"})

    client = make_client(handler)
    first = await client.search_dictionary_entries("strongsgreek", "  ΛΌΓΟΣ  ", limit=1)
    assert first.entries == [native["entries"][1]]
    assert (first.total, first.count, first.offset, first.next_offset) == (2, 1, 0, 1)
    assert first.query == "ΛΌΓΟΣ"
    assert first.source.service == "dictionaries"
    assert first.source.api_version == "v1"
    assert first.cache.cacheable
    assert 0 <= first.cache.remaining_ttl_seconds <= 60

    second = await client.search_dictionary_entries("strongsgreek", "λογος", limit=1, offset=1)
    assert second.entries == [native["entries"][2]]
    assert (second.total, second.count, second.offset, second.next_offset) == (2, 1, 1, None)
    assert native == original
    assert len(calls) == 2
    assert all(str(call.url) == "https://dictionaries.test/v1/strongsgreek/index.json" for call in calls)

    native["entries"][2]["key"] = "different"
    native["entries"][2]["search"] = "different"
    refreshed = await client.search_dictionary_entries("strongsgreek", "λογος")
    assert refreshed.total == 1
    assert len(calls) == 3


@pytest.mark.parametrize(
    ("query", "match", "ids"),
    [
        ("LOGOS", "exact", ["G3056"]),
        ("G3056--2", "exact", ["G3056--2"]),
        ("λο", "prefix", ["G3056", "G3056--2"]),
        ("γο", "contains", ["G3056", "G3056--2"]),  # noqa: RUF001 -- Greek lookup term
        ("STRASSE", "exact", ["fixture"]),
        ("road", "exact", ["fixture"]),
        ("G3056--3", "exact", []),
    ],
)
async def test_lookup_matches_keys_aliases_and_exact_ids(
    query: str, match: Any, ids: list[str]
) -> None:
    client = make_client(lambda _: httpx.Response(200, json=dictionary_index()))
    result = await client.search_dictionary_entries("strongsgreek", query, match=match)
    assert [entry["id"] for entry in result.entries] == ids
    assert result.total == result.count == len(ids)
    assert result.next_offset is None


async def test_lookup_preserves_record_extensions_and_empty_pagination() -> None:
    native = dictionary_index()
    native["entries"][1]["extension"] = {"relationships": [{"id": "G3004", "kind": "related"}]}
    client = make_client(lambda _: httpx.Response(200, json=native))
    result = await client.search_dictionary_entries("strongsgreek", "logos")
    assert result.entries == [native["entries"][1]]
    exhausted = await client.search_dictionary_entries("strongsgreek", "logos", offset=99)
    assert exhausted.entries == []
    assert (exhausted.total, exhausted.count, exhausted.offset, exhausted.next_offset) == (1, 0, 99, None)


@pytest.mark.parametrize(
    "parameters",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "\u0301"},
        {"query": "x" * 257},
        {"query": 2},
        {"match": "regex"},
        {"match": []},
        {"limit": 0},
        {"limit": 101},
        {"limit": 1.0},
        {"limit": True},
        {"offset": -1},
        {"offset": "0"},
        {"offset": False},
        {"dictionary": "../../"},
    ],
)
async def test_invalid_inputs_never_reach_upstream(parameters: dict[str, Any]) -> None:
    def reject_network(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid input must be rejected before making an upstream request")

    values = {"dictionary": "strongsgreek", "query": "logos", **parameters}
    with pytest.raises(InvalidRequestError):
        await make_client(reject_network).search_dictionary_entries(**values)


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "wrong-schema"},
        {"dictionary": "another-module"},
        {"entries": {}},
        {"entries": [{"id": "", "key": "word", "search": "word"}]},
        {"entries": [{"id": "word", "key": "word", "search": 1}]},
        {"entries": [{"id": "word", "key": "word", "search": "word", "aliases": "word"}]},
        {"entries": [{"id": "word", "key": "word", "search": "word", "aliases": [1]}]},
    ],
)
async def test_malformed_success_retains_native_failure_and_disables_caching(
    change: dict[str, Any],
) -> None:
    native = {**dictionary_index(), **change}
    client = make_client(
        lambda _: httpx.Response(200, json=native, headers={"cache-control": "max-age=60"})
    )
    with pytest.raises(UpstreamError, match="invalid dictionary index") as failed:
        await client.search_dictionary_entries("strongsgreek", "logos")
    assert failed.value.body == native
    assert failed.value.status_code == 200
    assert failed.value.result is not None
    assert failed.value.result.cache.cacheable is False
    assert failed.value.result.cache.remaining_ttl_seconds == 0


async def test_malformed_record_after_requested_page_still_fails() -> None:
    native = dictionary_index()
    native["entries"].append(None)
    client = make_client(lambda _: httpx.Response(200, json=native))
    with pytest.raises(UpstreamError, match="invalid dictionary index"):
        await client.search_dictionary_entries("strongsgreek", "logos", limit=1)


async def test_upstream_rate_limit_and_payload_size_limit_are_preserved() -> None:
    native = {"error": "rate_limited", "message": "Retry later"}
    client = make_client(
        lambda _: httpx.Response(429, json=native, headers={"retry-after": "45"})
    )
    with pytest.raises(UpstreamError) as failed:
        await client.search_dictionary_entries("strongsgreek", "logos")
    assert failed.value.status_code == 429
    assert failed.value.body == native
    assert failed.value.source is not None
    assert failed.value.source.headers["retry-after"] == "45"
    assert failed.value.result is not None
    assert failed.value.result.cache.cacheable is False

    bounded = make_client(
        lambda _: httpx.Response(200, json=dictionary_index()), max_response_bytes=100
    )
    with pytest.raises(UpstreamError, match="configured size limit"):
        await bounded.search_dictionary_entries("strongsgreek", "logos")


async def test_dictionary_lookup_over_mcp_validates_schema_and_preserves_native_errors() -> None:
    native = dictionary_index()
    requests: list[httpx.Request] = []
    problem = {"error": "rate_limited", "message": "Retry later"}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=native, headers={"cache-control": "max-age=60"})
        return httpx.Response(429, json=problem, headers={"retry-after": "45"})

    arguments = {"dictionary": "strongsgreek", "query": "ΛΌΓΟΣ", "limit": 1, "offset": 1}
    async with http_session(handler, path="/") as (session, _):
        tools = await session.list_tools()
        lookup = next(tool for tool in tools.tools if tool.name == "search_dictionary_entries")
        Draft202012Validator(lookup.input_schema).validate(arguments)
        assert lookup.input_schema["properties"]["limit"]["maximum"] == 100
        assert lookup.input_schema["properties"]["query"]["maxLength"] == 256
        result = structured_result(await session.call_tool("search_dictionary_entries", arguments))
        assert lookup.output_schema is not None
        assert lookup.output_schema["properties"]["entries"]["maxItems"] == 100
        Draft202012Validator(lookup.output_schema).validate(result)
        assert result["entries"] == [native["entries"][2]]
        assert result["total"] == 2
        assert result["count"] == 1
        assert result["next_offset"] is None
        assert result["source"]["url"].endswith("/v1/strongsgreek/index.json")

        failed = await session.call_tool("search_dictionary_entries", arguments)
        assert failed.is_error
        assert failed.structured_content is not None
        details = failed.structured_content["result"]
        assert details["data"] == problem
        assert details["source"]["status_code"] == 429
        assert details["source"]["headers"]["retry-after"] == "45"
        assert details["cache"]["cacheable"] is False
    assert len(requests) == 2


async def test_mcp_dictionary_lookup_rejects_invalid_paging_before_upstream() -> None:
    def reject_network(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid MCP arguments must not reach the upstream API")

    async with http_session(reject_network, path="/") as (session, _):
        for invalid in ({"limit": True}, {"limit": "1"}, {"offset": False}):
            result = await session.call_tool(
                "search_dictionary_entries",
                {"dictionary": "strongsgreek", "query": "logos", **invalid},
            )
            assert result.is_error
