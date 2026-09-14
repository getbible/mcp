from __future__ import annotations

import argparse
import asyncio
import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx2
import pytest
from test_server_http import http_session

from getbible_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checker(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("check_endpoint")


@pytest.mark.parametrize("url", [
    "https://mcp.example.org/", "https://mcp.example.org/custom",
    "http://127.0.0.1:8080/", "http://[::1]:8000/", "http://localhost/mcp",
])
def test_endpoint_accepts_tls_or_explicit_local_development(checker: ModuleType, url: str) -> None:
    assert checker.endpoint_url(url) == url


@pytest.mark.parametrize("url", [
    "http://mcp.example.org/", "https://token@mcp.example.org/",
    "https://mcp.example.org/?token=secret", "https://mcp.example.org/#secret",
    "file:///mcp", "https://", "https://mcp.example.org:invalid/",
    "https://mcp.example.org/\nsecret", "http://192.168.1.2/",
])
def test_endpoint_rejects_ambiguous_or_credential_bearing_urls(checker: ModuleType, url: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        checker.endpoint_url(url)


@pytest.fixture
def success() -> SimpleNamespace:
    return SimpleNamespace(is_error=False, structured_content={
        "data": {"chapter": {"verses": [{"verse": 16, "text": "For God so loved the world"}]}},
        "source": {"service": "query", "api_version": "v3", "status_code": 200},
        "cache": {"max_retention_seconds": 2592000, "remaining_ttl_seconds": 3600, "recommended": False},
    })


def test_native_verse_and_cache_metadata_are_verified(checker: ModuleType, success: Any) -> None:
    payload = checker.upstream_result(success, "query", "v3")
    assert checker.contains_verse(payload["data"])
    assert not checker.contains_verse({"status": "ok"})
    assert not checker.contains_verse({"verse": True, "text": "not a verse number"})
    assert not checker.contains_verse({"verse": 16, "text": "  "})


@pytest.mark.parametrize("fault", [
    "tool_error", "unstructured", "upstream_error", "wrong_version", "html",
    "missing_cache", "excess_retention", "excess_ttl", "cache_runtime",
])
def test_http_success_does_not_hide_protocol_upstream_or_content_failure(
    checker: ModuleType, success: Any, fault: str,
) -> None:
    payload = success.structured_content
    if fault == "tool_error":
        success.is_error = True
    elif fault == "unstructured":
        success.structured_content = None
    elif fault == "upstream_error":
        payload["source"]["status_code"] = 502
    elif fault == "wrong_version":
        payload["source"]["api_version"] = "v2"
    elif fault == "html":
        payload["data"] = "<html>proxy error</html>"
    elif fault == "missing_cache":
        payload.pop("cache")
    elif fault == "excess_retention":
        payload["cache"]["max_retention_seconds"] += 1
    elif fault == "excess_ttl":
        payload["cache"]["remaining_ttl_seconds"] = 2592001
    else:
        payload["cache"]["recommended"] = True
    with pytest.raises(checker.ProbeFailure):
        checker.upstream_result(success, "query", "v3")


def test_schema_validation_rejects_wrong_payload_and_remote_references(checker: ModuleType) -> None:
    schema = {"type": "object", "required": ["entries"], "properties": {"entries": {"type": "array"}}}
    checker.schema_check(schema, {"entries": []}, validate=True)
    with pytest.raises(checker.ProbeFailure, match="advertised JSON schema"):
        checker.schema_check(schema, {"status": "ok"}, validate=True)
    with pytest.raises(checker.ProbeFailure, match="external reference"):
        checker.schema_check({"$ref": "https://example.org/schema"}, {}, validate=True)


def test_catalog_selection_uses_published_ids_and_smallest_populated_dataset(checker: ModuleType) -> None:
    data = {"topics": [
        {"id": "large", "verses": 1000}, {"id": "empty", "verses": 0},
        {"id": "small", "verses": 1},
    ]}
    assert checker.smallest_item(data, "topics", "verses")["id"] == "small"
    with pytest.raises(checker.ProbeFailure, match="no populated"):
        checker.smallest_item({"topics": []}, "topics", "verses")


@pytest.mark.asyncio
async def test_probe_discovers_actual_sdk_server_without_upstream_network(checker: ModuleType) -> None:
    reports: list[str] = []
    probe = checker.Probe(report=reports.append)
    async with http_session(path="/") as (client, _):
        await probe.discovery(client, __version__)
    assert set(probe.documents) == checker.CONTRACTS
    assert len(reports) == 1 and reports[0].startswith("PASS MCP discovery")
    probe.validate_native("bookmarks", "v1", "getTopics", {"schema_version": 1, "topics": []})
    with pytest.raises(checker.ProbeFailure, match="advertised JSON schema"):
        probe.validate_native("bookmarks", "v1", "getTopics", {"status": "ok"})


@pytest.mark.asyncio
async def test_wrong_deployed_version_fails_before_listing_tools(checker: ModuleType) -> None:
    async with http_session(path="/") as (client, _):
        with pytest.raises(checker.ProbeFailure, match="package version"):
            await checker.Probe().discovery(client, "0.0.0")


@pytest.mark.asyncio
async def test_request_and_response_limits_fail_without_retries(
    checker: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = checker.Probe(timeout=0.01)
    with pytest.raises(TimeoutError):
        await probe.request("delayed call", asyncio.sleep(1))
    assert probe.current == "delayed call"
    probe.requests = checker.MAX_REQUESTS
    with pytest.raises(checker.ProbeFailure, match="request budget"):
        await probe.request_hook(httpx2.Request("POST", "https://example.org/"))
    for status in (401, 429, 502):
        with pytest.raises(checker.ProbeFailure):
            await probe.response_hook(httpx2.Response(status, text="sensitive error body"))
    monkeypatch.setattr(checker, "MAX_RESPONSE_BYTES", 3)
    stream = checker.LimitedStream(httpx2.ByteStream(b"four"))
    with pytest.raises(checker.ProbeFailure, match="probe limit"):
        _ = [chunk async for chunk in stream]
    await stream.aclose()


@pytest.mark.asyncio
async def test_complete_consumer_connection_uses_bounded_http_hooks_without_network(
    checker: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from getbible_mcp.client import GetBibleClient
    from getbible_mcp.server import create_runtime

    def reject_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Discovery must not use upstream HTTP: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reject_network)) as upstream:
        runtime = create_runtime(api_client=GetBibleClient(http_client=upstream), streamable_http_path="/")
        original_client = httpx2.AsyncClient

        def local_client(**kwargs: Any) -> httpx2.AsyncClient:
            return original_client(transport=httpx2.ASGITransport(app=runtime.app), **kwargs)

        monkeypatch.setattr(httpx2, "AsyncClient", local_client)
        monkeypatch.delenv("GETBIBLE_MCP_TOKEN", raising=False)
        probe = checker.Probe(report=lambda line: None)
        args = argparse.Namespace(url="http://localhost/", upstreams=False, expect_version=__version__)
        async with runtime.app.router.lifespan_context(runtime.app):
            await checker.run_probe(args, probe)
        assert 10 < probe.requests < checker.MAX_REQUESTS


def test_grouped_failures_do_not_print_remote_error_bodies(checker: ModuleType) -> None:
    failure = ExceptionGroup("private remote payload", [
        RuntimeError("private token or response data"),
        checker.ProbeFailure("HTTP 429: rate limited; wait before running again"),
    ])
    assert checker.failure_reason(failure) == "RuntimeError; HTTP 429: rate limited; wait before running again"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["tool", "resource"])
@pytest.mark.parametrize("expected", [None, "2.1.0"])
async def test_new_release_requires_study_tool_and_workflow_resource(
    checker: ModuleType, monkeypatch: pytest.MonkeyPatch, missing: str, expected: str | None,
) -> None:
    from unittest.mock import AsyncMock

    from mcp.types import ListResourcesResult, ListToolsResult

    async with http_session(path="/") as (client, _):
        version = "2.1.0"
        monkeypatch.setattr(type(client), "server_info", property(lambda self: SimpleNamespace(version=version)))
        tools = await client.list_tools()
        resources = await client.list_resources()
        if missing == "tool":
            tools = ListToolsResult(tools=[tool for tool in tools.tools if tool.name != "search_dictionary_entries"])
            monkeypatch.setattr(client, "list_tools", AsyncMock(return_value=tools))
        else:
            # Supply a semantically valid tool catalog even when this test runs against an older package.
            if "search_dictionary_entries" not in {tool.name for tool in tools.tools}:
                tools.tools.append(tools.tools[-1].model_copy(update={"name": "search_dictionary_entries"}))
            for tool in tools.tools:
                if tool.name in {"discover_apis", "describe_api_operation"}:
                    tool.annotations.open_world_hint = False
            monkeypatch.setattr(client, "list_tools", AsyncMock(return_value=tools))
            resources = ListResourcesResult(resources=[
                resource for resource in resources.resources if str(resource.uri) != "getbible://docs/study-workflows"
            ])
            monkeypatch.setattr(client, "list_resources", AsyncMock(return_value=resources))
        with pytest.raises(checker.ProbeFailure, match="missing"):
            await checker.Probe().discovery(client, expected)


@pytest.mark.parametrize("service", ["query", "search"])
@pytest.mark.parametrize("version", ["v2", "v3"])
def test_native_validation_resolves_real_versioned_response_schemas(
    checker: ModuleType, service: str, version: str,
) -> None:
    import json

    from getbible_mcp.contracts import ContractRegistry

    probe = checker.Probe()
    probe.documents[service, version] = ContractRegistry().document(service, version)
    groups = {"kjv_43_3": {
        "book_nr": 43, "chapter": 3,
        "verses": [{"verse": 16, "name": "John 3:16", "text": "For God so loved the world"}],
    }}
    if service == "query":
        data: Any = groups
        operation = "getScripture"
    else:
        data = {
            "query": {"text": "loved", "kind": "search", "translation": "kjv", "engine_version": 1, "total": 1, "returned": 1},
            "results": groups,
            "matches": [{"reference": "John 3:16", "book_nr": 43, "chapter": 3, "verse": 16}],
        }
        operation = "search"
    original = json.dumps(data)
    probe.validate_native(service, version, operation, data)
    assert json.dumps(data) == original
    with pytest.raises(checker.ProbeFailure, match="advertised JSON schema"):
        probe.validate_native(service, version, operation, {"status": "ok"})


@pytest.mark.asyncio
async def test_upstream_smoke_preserves_versions_and_uses_discovered_study_identifiers(
    checker: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    from getbible_mcp.contracts import ContractRegistry

    reports: list[str] = []
    probe = checker.Probe(report=reports.append)
    probe.documents = {key: ContractRegistry().document(*key) for key in checker.CONTRACTS}
    probe.tool_schemas["search_dictionary_entries"] = {"type": "object", "required": ["entries"]}
    calls: list[tuple[str, dict[str, Any]]] = []
    groups = {"kjv_43_3": {
        "book_nr": 43, "chapter": 3,
        "verses": [{"verse": 16, "name": "John 3:16", "text": "For God so loved the world"}],
    }}

    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        calls.append((name, arguments))
        version = arguments.get("api_version", "v1")
        if name == "list_books":
            data = {"43": {
                "translation": "King James Version", "abbreviation": "kjv", "lang": "en",
                "language": "English", "direction": "LTR", "encoding": "UTF-8", "nr": 43,
                "name": "John", "url": f"https://api.getbible.net/{version}/kjv/43.json", "sha": "a" * 40,
            }}
            service = "api"
        elif name == "query_verses":
            data, service = groups, "query"
        elif name == "search_verses":
            service = "search"
            data = {
                "query": {"text": "loved", "kind": "search", "translation": "kjv", "engine_version": 1, "total": 1, "returned": 1},
                "results": groups,
                "matches": [{"reference": "John 3:16", "book_nr": 43, "chapter": 3, "verse": 16}],
            }
        else:
            assert name == "search_dictionary_entries"
            assert arguments == {"dictionary": "selected-dictionary", "query": "published-key", "match": "exact", "limit": 1}
            data, service = {}, "dictionaries"
        payload = {
            "data": data,
            "source": {"service": service, "api_version": version, "status_code": 200},
            "cache": {"max_retention_seconds": 2592000, "remaining_ttl_seconds": 3600, "recommended": False},
        }
        if name == "search_dictionary_entries":
            payload.update(dictionary="selected-dictionary", entries=[{"id": "published-key"}], count=1)
            payload.pop("data")
        return SimpleNamespace(is_error=False, structured_content=payload)

    operations = {
        "listDictionaries": {"dictionaries": [{"id": "selected-dictionary", "entry_count": 1}]},
        "getDictionaryIndex": {"dictionary": "selected-dictionary", "entries": [{"id": "published-key"}]},
        "getDictionaryEntry": {"dictionary": "selected-dictionary", "id": "published-key"},
        "listCommentaries": {"commentaries": [{"id": "selected-commentary", "entry_count": 1}]},
        "getCommentaryBooks": {"commentary": "selected-commentary", "books": [{"book": 43, "chapters": [0]}]},
        "getCommentaryChapter": {"commentary": "selected-commentary", "book": 43, "chapter": 0, "entries": []},
        "getTopics": {"topics": [{"id": "selected-topic", "verses": 1}]},
        "getTopic": {"id": "selected-topic", "verses": [[43, 3, 16]]},
    }

    async def operation(client: Any, service: str, name: str, parameters: Any = None) -> Any:
        calls.append((name, parameters or {}))
        return operations[name]

    monkeypatch.setattr(probe, "operation", operation)
    await probe.upstreams(SimpleNamespace(call_tool=AsyncMock(side_effect=call_tool)))
    assert [(name, params["api_version"]) for name, params in calls if name == "list_books"] == [
        ("list_books", "v2"), ("list_books", "v3"),
    ]
    assert ("getDictionaryEntry", {"dictionary": "selected-dictionary", "entry": "published-key"}) in calls
    assert ("getCommentaryChapter", {"commentary": "selected-commentary", "book": 43, "chapter": 0}) in calls
    assert ("getTopic", {"id": "selected-topic"}) in calls
    assert len(reports) == 6
    operations["getCommentaryChapter"]["chapter"] = 1
    with pytest.raises(checker.ProbeFailure, match="published coordinates"):
        await probe.upstreams(SimpleNamespace(call_tool=AsyncMock(side_effect=call_tool)))
