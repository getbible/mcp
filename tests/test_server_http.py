from __future__ import annotations

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from getbible_mcp.config import Settings
from getbible_mcp.server import create_runtime


@pytest.mark.asyncio
async def test_streamable_http_initializes_at_exact_v2_with_all_capabilities() -> None:
    runtime = create_runtime(settings=Settings())

    async with runtime.app.router.lifespan_context(runtime.app):
        transport = httpx.ASGITransport(app=runtime.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            health = await http.get("/healthz")
            trailing = await http.get("/v2/")
            async with (
                streamable_http_client(
                    "http://testserver/v2",
                    http_client=http,
                    terminate_on_close=False,
                ) as (read_stream, write_stream, _),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                prompts = await session.list_prompts()

    assert health.status_code == 200
    assert health.json()["mcp_endpoint"] == "/v2"
    assert trailing.status_code == 404
    assert {tool.name for tool in tools.tools} == {
        "check_for_updates",
        "get_hash",
        "get_hash_manifest",
        "get_scripture",
        "list_books",
        "list_chapters",
        "list_translations",
        "query_verses",
    }
    assert {str(resource.uri) for resource in resources.resources} == {
        "getbible://docs/api-v2",
        "getbible://docs/cache-policy",
        "getbible://docs/usage-policy",
    }
    assert {prompt.name for prompt in prompts.prompts} == {"design_getbible_integration"}
