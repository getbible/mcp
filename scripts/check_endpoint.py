#!/usr/bin/env python3
"""Explicitly test a remote GetBible MCP connection; never runs as a scheduled job."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import re
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

import httpx2
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

CONTRACTS = {
    (service, version)
    for service, versions in (
        ("api", ("v2", "v3")), ("query", ("v2", "v3")), ("search", ("v2", "v3")),
        ("dictionaries", ("v1",)), ("commentaries", ("v1",)), ("bookmarks", ("v1",)),
    )
    for version in versions
}
REQUIRED_TOOLS = {
    "discover_apis", "describe_api_operation", "call_api_operation", "list_books",
    "query_verses", "search_verses", "check_for_updates", "get_hash", "get_hash_manifest",
    "get_scripture", "list_chapters", "list_translations",
}
DOCS = {"getbible://docs/api", "getbible://docs/cache-policy", "getbible://docs/usage-policy"}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REQUESTS = 64


class ProbeFailure(ValueError):
    """A readiness condition failed; messages contain no remote response bodies."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def endpoint_url(value: str) -> str:
    """Accept HTTPS endpoints and explicit loopback HTTP for local testing."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        loopback = host == "localhost"
        if not loopback:
            with suppress(ValueError):
                loopback = ipaddress.ip_address(host).is_loopback
        valid = (
            bool(host) and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment
            and (parsed.scheme == "https" or (parsed.scheme == "http" and loopback))
            and not any(char.isspace() for char in value)
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError(
            "Use an HTTPS MCP URL without credentials, query or fragment; HTTP is loopback-only."
        )
    return value


def schema_check(schema: Any, value: Any | None = None, *, validate: bool = False) -> None:
    """Validate locally without permitting a schema to fetch remote references."""
    require(isinstance(schema, dict), "Missing JSON schema")
    pending = [schema]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key in ("$ref", "$dynamicRef"):
                if key in item:
                    require(
                        isinstance(item[key], str) and item[key].startswith("#/"),
                        "Schema contains an unsupported external reference",
                    )
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    try:
        Draft202012Validator.check_schema(schema)
        if validate:
            Draft202012Validator(schema).validate(value)
    except Exception as exc:
        raise ProbeFailure("Response or arguments do not match the advertised JSON schema") from exc


def structured_result(result: Any) -> dict[str, Any]:
    require(not result.is_error, "MCP returned isError=true (HTTP 200 alone is not success)")
    require(isinstance(result.structured_content, dict), "Missing structured MCP result")
    return result.structured_content


def upstream_result(
    result: Any, service: str, version: str, *, data_field: str = "data",
) -> dict[str, Any]:
    payload = structured_result(result)
    source = payload.get("source", {})
    require(isinstance(source, dict), "Missing upstream provenance")
    require(source.get("status_code") == 200, "Upstream did not return HTTP 200")
    require(
        source.get("service") == service and source.get("api_version") == version,
        "Result came from an unexpected upstream service/version",
    )
    require(isinstance(payload.get(data_field), (dict, list)), "Upstream returned no JSON data")
    cache = payload.get("cache", {})
    require(isinstance(cache, dict), "Missing cache advice")
    maximum, remaining = cache.get("max_retention_seconds"), cache.get("remaining_ttl_seconds")
    require(
        type(maximum) is int and type(remaining) is int
        and 0 <= remaining <= maximum <= 30 * 24 * 60 * 60,
        "Cache advice exceeds the 30-day retention contract",
    )
    if service in {"query", "search"}:
        require(cache.get("recommended") is False, "Runtime response recommends caching")
    return payload


def contains_verse(data: Any) -> bool:
    """Accept native grouped query/search layouts without stripping v3 extensions."""
    pending = [data]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if (
                type(value.get("verse")) is int and isinstance(value.get("text"), str)
                and value["text"].strip()
            ):
                return True
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def smallest_item(data: dict[str, Any], collection: str, count: str) -> dict[str, Any]:
    entries = data.get(collection)
    require(isinstance(entries, list), "Catalog does not contain the expected collection")
    candidates = [
        item for item in entries
        if isinstance(item, dict) and isinstance(item.get("id"), str)
        and type(item.get(count)) is int and item[count] > 0
    ]
    require(candidates, "Catalog has no populated module/topic to test")
    return min(candidates, key=lambda item: item[count])


class LimitedStream(httpx2.AsyncByteStream):
    """Bound each wire response, including SSE data without Content-Length."""

    def __init__(self, stream: httpx2.AsyncByteStream) -> None:
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            require(size <= MAX_RESPONSE_BYTES, "MCP response exceeded the 16 MiB probe limit")
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


class Probe:
    def __init__(self, timeout: float = 30, report: Callable[[str], None] = print) -> None:
        self.timeout = timeout
        self.report = report
        self.current = "connection and protocol discovery"
        self.requests = 0
        self.documents: dict[tuple[str, str], dict[str, Any]] = {}
        self.tool_schemas: dict[str, dict[str, Any]] = {}

    async def request_hook(self, request: httpx2.Request) -> None:
        self.requests += 1
        require(self.requests <= MAX_REQUESTS, "Probe exceeded its 64-request budget")

    async def response_hook(self, response: httpx2.Response) -> None:
        # SDK transport errors may contain a remote body. Fail before it reads those bodies.
        require(response.status_code != 429, "HTTP 429: rate limited; wait before running again")
        require(response.status_code < 400, f"MCP HTTP request failed with {response.status_code}")
        require(
            response.headers.get("content-encoding", "identity") == "identity",
            "Probe requires an uncompressed response to enforce its size bound",
        )
        response.stream = LimitedStream(response.stream)

    async def request(self, label: str, operation: Awaitable[Any]) -> Any:
        self.current = label
        async with asyncio.timeout(self.timeout):
            return await operation

    def passed(self, label: str) -> None:
        self.report(f"PASS {label}")

    async def discovery(self, client: Client, expected_version: str | None) -> None:
        require(client.server_info is not None, "Server did not identify itself")
        if expected_version:
            require(client.server_info.version == expected_version, "Unexpected deployed package version")
        require(bool(client.instructions and client.instructions.strip()), "Missing server instructions")
        deployed_version = client.server_info.version
        require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", deployed_version), "Server did not report a stable package version")
        require_study = tuple(map(int, deployed_version.split("."))) >= (2, 1, 0)
        tools = await self.request("tool discovery", client.list_tools())
        names = {tool.name for tool in tools.tools}
        required_tools = REQUIRED_TOOLS | ({"search_dictionary_entries"} if require_study else set())
        require(names >= required_tools, "Required GetBible tools are missing")
        for tool in tools.tools:
            require(bool(tool.description and tool.description.strip()), "A tool has no description")
            annotations = tool.annotations
            require(
                annotations is not None and annotations.read_only_hint is True
                and annotations.destructive_hint is False and annotations.idempotent_hint is True
                and (annotations.open_world_hint is True if tool.name not in {
                    "discover_apis", "describe_api_operation",
                } else (annotations.open_world_hint is False if require_study else isinstance(annotations.open_world_hint, bool))),
                "A tool does not declare the expected read-only, external-data behavior",
            )
            schema_check(tool.input_schema)
            if tool.output_schema is not None:
                schema_check(tool.output_schema)
                self.tool_schemas[tool.name] = tool.output_schema
        resources = await self.request("resource discovery", client.list_resources())
        uris = {str(resource.uri) for resource in resources.resources}
        contract_uris = {f"getbible://openapi/{service}/{version}" for service, version in CONTRACTS}
        required_docs = DOCS | ({"getbible://docs/study-workflows"} if require_study else set())
        require(required_docs | contract_uris <= uris, "Required documentation or API contracts are missing")
        for uri in sorted(uris):
            if not (uri.startswith("getbible://docs/") or uri in contract_uris):
                continue
            resource = await self.request("documentation resource", client.read_resource(uri))
            require(len(resource.contents) == 1, "Unexpected documentation resource contents")
            content = resource.contents[0]
            require(isinstance(getattr(content, "text", None), str) and content.text.strip(), "Empty resource")
            if uri in contract_uris:
                document = json.loads(content.text)
                require(isinstance(document, dict) and document.get("paths"), "Invalid OpenAPI resource")
                service, version = uri.rsplit("/", 2)[1:]
                self.documents[service, version] = document
        catalog = structured_result(await self.request("API catalog", client.call_tool("discover_apis", {})))
        require(
            {(item["service"], item["version"]) for item in catalog.get("apis", [])} == CONTRACTS,
            "API catalog does not cover the nine supported contracts",
        )
        prompts = await self.request("prompt discovery", client.list_prompts())
        integration = next((prompt for prompt in prompts.prompts if prompt.name == "design_getbible_integration"), None)
        require(integration is not None and integration.description, "Integration prompt is missing or undocumented")
        arguments = {argument.name: argument for argument in integration.arguments or []}
        require("application" in arguments and arguments["application"].required is True, "Integration prompt does not document its required application argument")
        prompt = await self.request("integration prompt", client.get_prompt(
            "design_getbible_integration", {"application": "A read-only Bible study application."},
        ))
        require(prompt.messages and all(
            message.content.type == "text" and message.content.text.strip()
            for message in prompt.messages
        ), "Integration prompt returned no readable instructions")
        self.passed(f"MCP discovery, {len(names)} documented tools, documentation, nine contracts and integration prompt")

    def validate_native(self, service: str, version: str, operation: str, data: Any) -> None:
        document = self.documents[service, version]
        for path in document["paths"].values():
            for method in ("get", "post"):
                definition = path.get(method, {})
                if definition.get("operationId") != operation:
                    continue
                response = definition["responses"]["200"]
                seen: set[str] = set()
                while "$ref" in response:
                    reference = response["$ref"]
                    require(isinstance(reference, str) and reference.startswith("#/") and reference not in seen, "Unsupported response reference")
                    seen.add(reference)
                    response = document
                    for part in reference[2:].split("/"):
                        response = response[part.replace("~1", "/").replace("~0", "~")]
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                require(isinstance(schema, dict), "Operation has no JSON success schema")
                schema_check({**schema, "components": document.get("components", {})}, data, validate=True)
                return
        raise ProbeFailure("Operation missing from advertised contract")

    async def operation(
        self, client: Client, service: str, operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> Any:
        arguments = {"service": service, "api_version": "v1", "operation_id": operation}
        description = structured_result(await self.request(
            f"{service}: operation schema", client.call_tool("describe_api_operation", arguments),
        ))
        require(description.get("method") == "GET", "Probe operation is not a read-only GET")
        schema_check(description.get("input_schema"), {"parameters": parameters or {}}, validate=True)
        result = await self.request(
            f"{service}: {operation}",
            client.call_tool("call_api_operation", {**arguments, "parameters": parameters or {}}),
        )
        data = upstream_result(result, service, "v1")["data"]
        self.validate_native(service, "v1", operation, data)
        return data

    async def upstreams(self, client: Client) -> None:
        for version in ("v2", "v3"):
            books = upstream_result(await self.request(
                f"api/{version}: books", client.call_tool("list_books", {"translation": "kjv", "api_version": version}),
            ), "api", version)["data"]
            self.validate_native("api", version, "listBooks" if version == "v2" else "getBooks", books)
            require(bool(books), "Bible book catalog is empty")
            for service, name, arguments in (
                ("query", "query_verses", {"references": "John 3:16"}),
                ("search", "search_verses", {"search": "loved", "book": [43], "limit": 1}),
            ):
                result = await self.request(f"{service}/{version}", client.call_tool(
                    name, {**arguments, "translation": "kjv", "api_version": version},
                ))
                data = upstream_result(result, service, version)["data"]
                self.validate_native(service, version, "getScripture" if service == "query" else "search", data)
                require(contains_verse(data), "Query/search did not return a nonempty verse")
                if service == "query":
                    require(
                        any(group.get("book_nr") == 43 and group.get("chapter") == 3
                            and any(verse.get("verse") == 16 for verse in group["verses"])
                            for group in data.values()),
                        "Reference query returned a different passage",
                    )
                else:
                    require(len(data["matches"]) == 1, "Search did not respect the one-result limit")
            self.passed(f"Bible catalog, reference query and limited search ({version})")
        dictionaries = await self.operation(client, "dictionaries", "listDictionaries")
        dictionary = smallest_item(dictionaries, "dictionaries", "entry_count")["id"]
        index = await self.operation(client, "dictionaries", "getDictionaryIndex", {"dictionary": dictionary})
        require(index["dictionary"] == dictionary, "Dictionary index came from a different module")
        require(bool(index["entries"]), "Dictionary index is empty")
        entry_id = index["entries"][0]["id"]
        if "search_dictionary_entries" in self.tool_schemas:
            lookup = upstream_result(await self.request(
                "dictionaries: bounded entry lookup",
                client.call_tool("search_dictionary_entries", {
                    "dictionary": dictionary, "query": entry_id, "match": "exact", "limit": 1,
                }),
            ), "dictionaries", "v1", data_field="entries")
            schema_check(self.tool_schemas["search_dictionary_entries"], lookup, validate=True)
            require(lookup["dictionary"] == dictionary and lookup["count"] == 1
                    and len(lookup["entries"]) == 1 and lookup["entries"][0]["id"] == entry_id,
                    "Dictionary lookup did not return the requested published entry")
            entry_id = lookup["entries"][0]["id"]
            self.passed("Bounded dictionary lookup returns a published entry ID")
        entry = await self.operation(client, "dictionaries", "getDictionaryEntry", {"dictionary": dictionary, "entry": entry_id})
        require(entry.get("id") == entry_id and entry.get("dictionary") == dictionary, "Dictionary entry does not match its index/module")
        self.passed("Dictionary catalog → smallest module index → exact entry")
        commentaries = await self.operation(client, "commentaries", "listCommentaries")
        commentary = smallest_item(commentaries, "commentaries", "entry_count")["id"]
        books = await self.operation(client, "commentaries", "getCommentaryBooks", {"commentary": commentary})
        require(books["commentary"] == commentary, "Commentary index came from a different module")
        book = next((item for item in books["books"] if item.get("chapters")), None)
        require(book is not None, "Commentary has no published chapter")
        chapter = await self.operation(client, "commentaries", "getCommentaryChapter", {
            "commentary": commentary, "book": book["book"], "chapter": book["chapters"][0],
        })
        require(chapter["commentary"] == commentary and chapter["book"] == book["book"]
                and chapter["chapter"] == book["chapters"][0], "Commentary chapter does not match published coordinates")
        self.passed("Commentary catalog → published books/chapters → chapter")
        topics = await self.operation(client, "bookmarks", "getTopics")
        topic_id = smallest_item(topics, "topics", "verses")["id"]
        topic = await self.operation(client, "bookmarks", "getTopic", {"id": topic_id})
        require(topic.get("id") == topic_id and topic.get("verses"), "Bookmark topic has no matching verse data")
        self.passed("Public bookmark topic summaries → smallest populated topic")


async def run_probe(args: argparse.Namespace, probe: Probe) -> None:
    token = os.environ.get("GETBIBLE_MCP_TOKEN")
    require(token is None or (token.strip() and not any(char.isspace() for char in token)), "Invalid GETBIBLE_MCP_TOKEN")
    headers = {"Accept-Encoding": "identity"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with (
        asyncio.timeout(300),
        httpx2.AsyncClient(
            headers=headers, timeout=httpx2.Timeout(probe.timeout, connect=min(probe.timeout, 10)),
            event_hooks={"request": [probe.request_hook], "response": [probe.response_hook]},
        ) as http,
        Client(
            streamable_http_client(args.url, http_client=http, terminate_on_close=False),
            cache=None, read_timeout_seconds=probe.timeout,
        ) as client,
    ):
        await probe.discovery(client, args.expect_version)
        if args.upstreams:
            await probe.upstreams(client)
        else:
            probe.report("SKIP upstream requests (run with --upstreams to test all nine API contracts)")


def failure_reason(error: BaseException) -> str:
    """Unwrap SDK task groups without printing their potentially sensitive remote messages."""
    if isinstance(error, ProbeFailure):
        return str(error)
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(dict.fromkeys(failure_reason(item) for item in error.exceptions))
    return type(error).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", type=endpoint_url, default="https://mcp.getbible.net/")
    parser.add_argument("--upstreams", action="store_true", help="Also make representative read-only calls to all nine API contracts")
    parser.add_argument("--expect-version", help="Fail unless discovery reports this exact package version")
    parser.add_argument("--timeout", type=int, choices=range(1, 61), default=30, metavar="1..60", help="Per-call timeout in seconds (default: 30; total run limited to 300)")
    args = parser.parse_args()
    if args.expect_version and not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.expect_version):
        parser.error("--expect-version must be a stable MAJOR.MINOR.PATCH version")
    # Do not echo remote error bodies, endpoint paths or authentication material from SDK loggers.
    logging.disable(logging.CRITICAL)
    probe = Probe(timeout=args.timeout)
    try:
        asyncio.run(run_probe(args, probe))
    except (Exception, KeyboardInterrupt) as exc:
        reason = failure_reason(exc)
        print(f"FAIL {probe.current}: {reason}. No full readiness pass was recorded.", file=sys.stderr)
        return 1
    print(f"PASS requested checks complete ({probe.requests} HTTP requests); ChatGPT connection/review still requires manual testing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
