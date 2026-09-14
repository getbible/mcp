from __future__ import annotations

import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_subprocess_initializes_and_lists_same_tools() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "getbible_mcp", "--transport", "stdio"],
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        resources = await session.list_resources()
        catalog = await session.call_tool("discover_apis", {})
        description = await session.call_tool(
            "describe_api_operation",
            {
                "service": "search",
                "api_version": "v3",
                "operation_id": "searchPost",
            },
        )
        contract = await session.read_resource("getbible://openapi/query/v3")
        guide = await session.read_resource("getbible://docs/cache-policy")
        prompts = await session.list_prompts()

    assert {tool.name for tool in tools.tools} == {
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
    assert all(tool.annotations and tool.annotations.readOnlyHint for tool in tools.tools)
    assert {str(resource.uri) for resource in resources.resources} == {
        "getbible://docs/api",
        "getbible://docs/api-v2",
        "getbible://docs/cache-policy",
        "getbible://docs/usage-policy",
        "getbible://openapi/api/v2",
        "getbible://openapi/api/v3",
        "getbible://openapi/query/v2",
        "getbible://openapi/query/v3",
        "getbible://openapi/search/v2",
        "getbible://openapi/search/v3",
        "getbible://openapi/dictionaries/v1",
        "getbible://openapi/commentaries/v1",
        "getbible://openapi/bookmarks/v1",
    }
    assert not catalog.isError
    assert catalog.structuredContent is not None
    assert {
        (entry["service"], entry["version"]) for entry in catalog.structuredContent["apis"]
    } == {
        ("api", "v2"),
        ("api", "v3"),
        ("query", "v2"),
        ("query", "v3"),
        ("search", "v2"),
        ("search", "v3"),
        ("dictionaries", "v1"),
        ("commentaries", "v1"),
        ("bookmarks", "v1"),
    }
    assert not description.isError
    assert description.structuredContent is not None
    assert description.structuredContent["method"] == "POST"
    assert description.structuredContent["path"] == "/v3/{translation}/{search}"
    query = json.loads(contract.contents[0].text)
    assert query["paths"]["/v3/{translation}/{reference}"]["get"]["operationId"] == "getScripture"
    assert guide.contents[0].mimeType == "text/markdown"
    assert guide.contents[0].text.strip()
    assert {prompt.name for prompt in prompts.prompts} == {"design_getbible_integration"}
