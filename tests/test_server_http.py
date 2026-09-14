from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any

import httpx
import httpx2
import pytest
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types.version import LATEST_PROTOCOL_VERSION
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from getbible_mcp.client import GetBibleClient
from getbible_mcp.config import Settings
from getbible_mcp.server import create_runtime

TOOL_NAMES = {
    "call_api_operation",
    "check_for_updates",
    "describe_api_operation",
    "discover_apis",
    "get_hash",
    "get_hash_manifest",
    "get_scripture",
    "list_books",
    "list_chapters",
    "list_translations",
    "query_verses",
    "search_verses",
}
API_VERSIONS = {
    "api": ("v2", "v3"),
    "query": ("v2", "v3"),
    "search": ("v2", "v3"),
    "dictionaries": ("v1",),
    "commentaries": ("v1",),
    "bookmarks": ("v1",),
}
DOC_URIS = {
    "getbible://docs/api",
    "getbible://docs/cache-policy",
    "getbible://docs/usage-policy",
}
CONTRACT_URIS = {
    f"getbible://openapi/{service}/{version}"
    for service, versions in API_VERSIONS.items()
    for version in versions
}


def reject_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Discovery must not request upstream data: {request.url}")


@asynccontextmanager
async def http_session(
    handler: Callable[[httpx.Request], httpx.Response] = reject_network,
    *,
    path: str = "/mcp",
) -> AsyncIterator[tuple[Client, httpx2.AsyncClient]]:
    settings = Settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
        client = GetBibleClient(settings=settings, http_client=upstream)
        runtime = create_runtime(settings=settings, api_client=client, streamable_http_path=path)
        async with runtime.app.router.lifespan_context(runtime.app):
            transport = httpx2.ASGITransport(app=runtime.app)
            async with (
                httpx2.AsyncClient(transport=transport, base_url="http://testserver") as http,
                Client(
                    streamable_http_client(
                        f"http://testserver{path}",
                        http_client=http,
                        terminate_on_close=False,
                    ),
                    cache=None,
                ) as session,
            ):
                assert session.protocol_version == LATEST_PROTOCOL_VERSION
                yield session, http


def structured_result(result: Any) -> dict[str, Any]:
    assert not result.is_error, result.content
    assert isinstance(result.structured_content, dict)
    return result.structured_content


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/mcp", "/"])
async def test_streamable_http_exposes_versioned_tools_and_readable_contracts(path: str) -> None:
    async with http_session(path=path) as (session, http):
        health = await http.get("/healthz")
        trailing = await http.get("/mcp/")
        tools = await session.list_tools()
        resources = await session.list_resources()
        prompts = await session.list_prompts()

        assert health.status_code == 200
        assert health.json()["mcp_endpoint"] == path
        assert trailing.status_code == 404
        if path == "/":
            assert (await http.post("/mcp", json={})).status_code == 404
        assert {tool.name for tool in tools.tools} == TOOL_NAMES
        assert {str(resource.uri) for resource in resources.resources} == DOC_URIS | CONTRACT_URIS
        assert {prompt.name for prompt in prompts.prompts} == {"design_getbible_integration"}

        for tool in tools.tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.open_world_hint is True
            Draft202012Validator.check_schema(tool.input_schema)
            if tool.output_schema is not None:
                Draft202012Validator.check_schema(tool.output_schema)

        for uri in sorted(CONTRACT_URIS):
            resource = await session.read_resource(uri)
            assert len(resource.contents) == 1
            content = resource.contents[0]
            assert content.mime_type == "application/json"
            document = json.loads(content.text)
            assert document["openapi"].startswith("3.")
            assert document["paths"]
            service, version = uri.rsplit("/", 2)[1:]
            expected = json.loads(
                files("getbible_mcp")
                .joinpath(
                    "openapi",
                    f"{service}-{version}.json",
                )
                .read_text(encoding="utf-8")
            )
            assert document == expected

        for uri in sorted(DOC_URIS):
            resource = await session.read_resource(uri)
            assert resource.contents[0].mime_type == "text/markdown"
            assert resource.contents[0].text.strip()


@pytest.mark.asyncio
async def test_query_preserves_native_v3_content_and_fetches_each_time() -> None:
    calls: list[httpx.Request] = []
    payload = {
        "kjv_43_3": {
            "translation": "King James Version",
            "book_nr": 43,
            "chapter": 3,
            "verses": [
                {
                    "verse": 16,
                    "name": "John 3:16",
                    "text": "For God so loved the world",
                    "paragraph": True,
                    "tokens": [
                        {
                            "token": "God",
                            "lemma": {"strong": ["G2316"]},
                            "word_start": 2,
                            "word_end": 2,
                            "source_extension": {"values": [1, None, {"text": "θεός"}]},
                        }
                    ],
                    "spans": [{"tag": "q", "attrs": {"who": "Jesus"}}],
                }
            ],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "query.getbible.net"
        assert request.url.path == "/v3/kjv/John 3:16"
        assert not request.url.query
        return httpx.Response(
            200,
            json=payload,
            headers={"cache-control": "public, max-age=3600", "etag": 'W/"revision"'},
        )

    async with http_session(handler) as (session, _):
        for _ in range(2):
            result = structured_result(
                await session.call_tool(
                    "query_verses",
                    {"translation": "kjv", "references": "John 3:16", "api_version": "v3"},
                )
            )
            assert result["data"] == payload
            assert result["source"]["api_version"] == "v3"
            assert result["source"]["service"] == "query"
            assert result["source"]["headers"]["etag"] == 'W/"revision"'
            assert result["cache"]["recommended"] is False
            assert result["cache"]["remaining_ttl_seconds"] <= 3600

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_discovery_describes_complete_search_inputs_without_network() -> None:
    async with http_session() as (session, _):
        catalog = structured_result(await session.call_tool("discover_apis", {}))
        assert {(entry["service"], entry["version"]) for entry in catalog["apis"]} == {
            (service, version) for service, versions in API_VERSIONS.items() for version in versions
        }
        operations = structured_result(
            await session.call_tool(
                "describe_api_operation",
                {"service": "search", "api_version": "v3"},
            )
        )
        assert {operation["operation_id"] for operation in operations["operations"]} >= {
            "search",
            "searchPost",
            "searchDefault",
            "searchDefaultPost",
        }
        description = structured_result(
            await session.call_tool(
                "describe_api_operation",
                {"service": "search", "api_version": "v3", "operation_id": "searchPost"},
            )
        )

    assert description["method"] == "POST"
    assert description["path"] == "/v3/{translation}/{search}"
    parameters = {item["input_name"]: item for item in description["parameters"]}
    assert parameters["translation"]["in"] == "path"
    assert parameters["query.translation"]["in"] == "query"
    assert parameters["book"]["explode"] is True
    Draft202012Validator.check_schema(description["input_schema"])
    validator = Draft202012Validator(description["input_schema"])
    validator.validate(
        {
            "parameters": {"translation": "kjv", "search": "faith", "book": ["Genesis", 2]},
            "body": {"limit": 25, "proximity": None},
        }
    )
    assert list(
        validator.iter_errors(
            {
                "parameters": {"translation": "kjv", "search": "faith", "limit": 101},
            }
        )
    )


@pytest.mark.asyncio
async def test_search_serializes_repeated_filters_and_preserves_native_metadata() -> None:
    calls: list[httpx.Request] = []
    payload = {
        "query": {
            "kind": "search",
            "total": 2,
            "returned": 1,
            "has_more": True,
            "offset": 0,
            "limit": 1,
            "sha": "a" * 40,
            "cache": {"checked_at": 1000.0, "stale": False},
        },
        "results": {"kjv_1_1": {"book_nr": 1, "chapter": 1, "verses": []}},
        "matches": [
            {
                "reference": "Genesis 1:1",
                "book_nr": 1,
                "chapter": 1,
                "verse": 1,
                "score": 4.2,
                "terms": ["faith"],
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "search.getbible.net"
        assert request.url.path == "/v3/kjv/faith hope"
        assert request.url.params.get_list("book") == ["Genesis", "2"]
        assert request.url.params.get_list("exclude") == ["evil", "fear"]
        assert request.url.params["case_sensitive"] == "false"
        assert request.url.params["limit"] == "1"
        assert request.url.params["proximity"] == "3"
        return httpx.Response(200, json=payload, headers={"cache-control": "no-store"})

    async with http_session(handler) as (session, _):
        result = structured_result(
            await session.call_tool(
                "search_verses",
                {
                    "search": "faith hope",
                    "translation": "kjv",
                    "api_version": "v3",
                    "book": ["Genesis", 2],
                    "exclude": ["evil", "fear"],
                    "limit": 1,
                    "proximity": 3,
                },
            )
        )

    assert len(calls) == 1
    assert result["data"] == payload
    assert result["source"]["api_version"] == "v3"
    assert result["cache"]["cacheable"] is False
    assert result["cache"]["recommended"] is False


@pytest.mark.asyncio
async def test_generic_search_supports_read_only_post_and_parameter_precedence() -> None:
    calls: list[httpx.Request] = []
    payload = {"query": {"kind": "search", "returned": 0}, "results": {}, "matches": []}
    body = {"q": "body words", "limit": 25, "proximity": None}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v3/kjv/path words"
        assert request.url.params["translation"] == "web"
        assert request.url.params["q"] == "query words"
        assert request.url.params.get_list("exclude") == ["evil", "fear"]
        assert json.loads(request.content) == body
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(200, json=payload, headers={"cache-control": "no-store"})

    async with http_session(handler) as (session, _):
        result = structured_result(
            await session.call_tool(
                "call_api_operation",
                {
                    "service": "search",
                    "api_version": "v3",
                    "operation_id": "searchPost",
                    "parameters": {
                        "translation": "kjv",
                        "query.translation": "web",
                        "search": "path words",
                        "q": "query words",
                        "exclude": ["evil", "fear"],
                    },
                    "body": body,
                },
            )
        )

    assert len(calls) == 1
    assert result["data"] == payload
    assert result["cache"]["cacheable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status, code", [(404, "invalid_reference"), (429, "rate_limited")])
@pytest.mark.parametrize("tool_name", ["call_api_operation", "query_verses", "search_verses"])
async def test_upstream_problem_is_reported_as_mcp_tool_error(
    status: int,
    code: str,
    tool_name: str,
) -> None:
    problem = {
        "type": "about:blank",
        "title": "Request failed",
        "status": status,
        "code": code,
        "detail": "The upstream service rejected this request.",
        "instance": "/v3/kjv/John3:999",
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json=problem,
            headers={"content-type": "application/problem+json", "retry-after": "7"},
        )

    arguments: dict[str, Any]
    if tool_name == "call_api_operation":
        arguments = {
            "service": "query",
            "api_version": "v3",
            "operation_id": "getScripture",
            "parameters": {"translation": "kjv", "reference": "John3:999"},
        }
    elif tool_name == "query_verses":
        arguments = {"references": "John3:999", "api_version": "v3"}
    else:
        arguments = {"search": "faith", "api_version": "v3"}

    async with http_session(handler) as (session, _):
        result = await session.call_tool(tool_name, arguments)

    assert result.is_error is True
    assert result.structured_content is not None
    native = result.structured_content["result"]
    assert native["data"] == problem
    assert native["source"]["status_code"] == status
    assert native["source"]["headers"]["retry-after"] == "7"
    text = "\n".join(block.text for block in result.content if block.type == "text")
    assert str(status) in text
    assert code in text
    assert problem["detail"] in text
    if status == 429:
        assert "7" in text


@pytest.mark.asyncio
async def test_invalid_tool_inputs_fail_before_upstream_request() -> None:
    async with http_session() as (session, _):
        invalid_version = await session.call_tool(
            "query_verses",
            {"translation": "kjv", "references": "John3:16", "api_version": "v1"},
        )
        missing_reference = await session.call_tool(
            "query_verses",
            {"translation": "kjv", "references": "", "api_version": "v3"},
        )

    assert invalid_version.is_error is True
    assert missing_reference.is_error is True


class TrackingClient(GetBibleClient):
    close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        await super().close()


def owned_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[TrackingClient, httpx.AsyncClient]:
    """Exercise client ownership with an actual HTTP client using an offline transport."""
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with monkeypatch.context() as patch:
        patch.setattr("getbible_mcp.client.httpx.AsyncClient", lambda **_: upstream)
        client = TrackingClient(settings=Settings())
    return client, upstream


@pytest.mark.asyncio
async def test_http_client_lives_until_application_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"kjv": {"name": "King James Version"}})

    client, upstream = owned_client(monkeypatch, handler)
    runtime = create_runtime(
        settings=Settings(),
        api_client=client,
        streamable_http_path="/bridge",
    )
    async with runtime.app.router.lifespan_context(runtime.app):
        async with (
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=runtime.app),
                base_url="http://testserver",
            ) as http,
            Client(
                streamable_http_client(
                    "http://testserver/bridge",
                    http_client=http,
                    terminate_on_close=False,
                ),
                cache=None,
            ) as session,
        ):
            assert session.protocol_version == LATEST_PROTOCOL_VERSION
            assert client.close_calls == 0
            assert not upstream.is_closed
            health = await http.get("/healthz")
            assert health.json()["mcp_endpoint"] == "/bridge"
            for version in ("v2", "v3"):
                result = structured_result(
                    await session.call_tool(
                        "list_translations",
                        {"api_version": version},
                    )
                )
                assert result["data"]["kjv"]["name"] == "King James Version"
                assert client.close_calls == 0
                assert not upstream.is_closed
        assert client.close_calls == 0
        assert not upstream.is_closed

    assert calls == ["/v2/translations.json", "/v3/translations.json"]
    assert client.close_calls == 1
    assert upstream.is_closed


@pytest.mark.asyncio
async def test_package_factory_embeds_at_mcp_with_parent_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from getbible_mcp import create_app

    client, upstream = owned_client(monkeypatch, reject_network)
    child = create_app(settings=Settings(), api_client=client)

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with child.router.lifespan_context(child):
            yield

    async def host_health(_: Request) -> JSONResponse:
        return JSONResponse({"host": "ready"})

    parent = Starlette(
        routes=[Route("/host-health", host_health), Mount("/", app=child)],
        lifespan=lifespan,
    )
    async with (
        parent.router.lifespan_context(parent),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=parent),
            base_url="http://testserver",
        ) as http,
        Client(
            streamable_http_client(
                "http://testserver/mcp",
                http_client=http,
                terminate_on_close=False,
            ),
            cache=None,
        ) as session,
    ):
        assert session.protocol_version == LATEST_PROTOCOL_VERSION
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == TOOL_NAMES
        catalog = structured_result(await session.call_tool("discover_apis", {}))
        assert len(catalog["apis"]) == 9
        assert (await http.get("/host-health")).json() == {"host": "ready"}
        assert (await http.get("/healthz")).json()["mcp_endpoint"] == "/mcp"
        assert (await http.get("/mcp/")).status_code == 404
        assert client.close_calls == 0
        assert not upstream.is_closed

    assert client.close_calls == 1
    assert upstream.is_closed
