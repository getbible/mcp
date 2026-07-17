from __future__ import annotations

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

