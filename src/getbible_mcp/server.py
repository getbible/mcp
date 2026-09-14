"""GetBible MCP tools, resources, prompts, and Streamable HTTP application."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Icon, TextContent, ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from getbible_mcp import __version__
from getbible_mcp.client import CACHE_POLICY, GetBibleClient, GetBibleError, UpstreamError
from getbible_mcp.config import Settings
from getbible_mcp.contracts import ContractRegistry
from getbible_mcp.guidance import (
    API_GUIDE,
    CACHE_GUIDE,
    SERVER_INSTRUCTIONS,
    STUDY_GUIDE,
    USAGE_GUIDE,
)
from getbible_mcp.models import (
    ApiResult,
    DictionarySearchResult,
    HashResult,
    HashWatch,
    ManifestKind,
    ManifestResult,
    MappingResult,
    QueryResult,
    ScopeKind,
    ScopeSpec,
    ScriptureResult,
    UpdateCheckResult,
    UpdateItem,
)

BibleVersion = Literal["v2", "v3"]
ApiVersion = Literal["v1", "v2", "v3"]
Service = Literal["api", "query", "search", "dictionaries", "commentaries", "bookmarks"]
CONTRACTS = (
    ("api", "v2"),
    ("api", "v3"),
    ("query", "v2"),
    ("query", "v3"),
    ("search", "v2"),
    ("search", "v3"),
    ("dictionaries", "v1"),
    ("commentaries", "v1"),
    ("bookmarks", "v1"),
)


class GetBibleMCP(MCPServer[Any]):
    """Preserve native upstream errors for every tool, including typed convenience tools."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context[Any, Any] | None = None,
    ) -> Any:
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            cause: BaseException | None = exc
            while cause is not None:
                if isinstance(cause, UpstreamError):
                    payload = cause.to_dict()
                    return CallToolResult(
                        is_error=True,
                        content=[
                            TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))
                        ],
                        structured_content=payload,
                    )
                cause = cause.__cause__
            raise


@dataclass(frozen=True)
class ServerRuntime:
    mcp: Any
    app: Any
    client: GetBibleClient
    settings: Settings


def create_runtime(
    settings: Settings | None = None,
    api_client: GetBibleClient | None = None,
    *,
    streamable_http_path: str = "/mcp",
) -> ServerRuntime:
    """Create identical isolated runtimes for local and hosted clients."""
    resolved_settings = settings or Settings.from_env()
    if (
        not streamable_http_path.startswith("/")
        or streamable_http_path == "/healthz"
        or any(char in streamable_http_path for char in "?#{}")
        or "//" in streamable_http_path
        or (streamable_http_path != "/" and streamable_http_path.endswith("/"))
        or any(part in {".", ".."} for part in streamable_http_path.split("/"))
    ):
        raise ValueError("streamable_http_path must be an exact absolute endpoint path")
    resolved_client = api_client or GetBibleClient(settings=resolved_settings)
    registry = ContractRegistry()

    @asynccontextmanager
    async def lifespan(_: Any) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await resolved_client.close()

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(resolved_settings.allowed_hosts),
        allowed_origins=list(resolved_settings.allowed_origins),
    )
    server = GetBibleMCP(
        name="GetBible",
        title="GetBible",
        description="Read and search Bible translations, dictionaries, commentaries and public topics.",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://getbible.life",
        icons=[
            Icon(
                src="data:image/png;base64,"
                + base64.b64encode(
                    files("getbible_mcp").joinpath("assets", "icon.png").read_bytes()
                ).decode("ascii"),
                mime_type="image/png",
                sizes=["230x230"],
            )
        ],
        lifespan=lifespan,
    )
    read_only = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )
    local_read_only = read_only.model_copy(update={"open_world_hint": False})

    @server.tool(title="Discover GetBible APIs", annotations=local_read_only)
    def discover_apis(
        service: Service | None = None,
        api_version: ApiVersion | None = None,
    ) -> dict[str, Any]:
        """Discover supported service/version contracts and their OpenAPI resources. Start here."""
        entries = registry.catalog()
        return {
            "apis": [
                entry
                for entry in entries
                if (service is None or entry["service"] == service)
                and (api_version is None or entry["version"] == api_version)
            ]
        }

    @server.tool(title="Describe GetBible API operations", annotations=local_read_only)
    def describe_api_operation(
        service: Service,
        api_version: ApiVersion,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """List operations, or inspect one exact input schema, response schema and parameter meanings.

        Use the returned input_schema for call_api_operation. Names are scoped by service/version.
        """
        if operation_id is not None:
            return registry.describe(service, api_version, operation_id)
        document = registry.document(service, api_version)
        return {
            "service": service,
            "version": api_version,
            "operations": [
                {
                    "operation_id": operation["operationId"],
                    "method": method.upper(),
                    "path": path,
                    "summary": operation.get("summary", ""),
                }
                for path, item in document["paths"].items()
                for method, operation in item.items()
                if method in {"get", "post"} and isinstance(operation, dict)
            ],
        }

    @server.tool(
        title="Call a documented GetBible operation", annotations=read_only, structured_output=False
    )
    async def call_api_operation(
        service: Service,
        api_version: ApiVersion,
        operation_id: str,
        parameters: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Execute any operation discovered with describe_api_operation using its exact input schema.

        Only reviewed routes and read-only methods are accepted. parameters holds named path/query
        inputs; body is only for documented search POST JSON. Native JSON/text is returned in data,
        with source/status/headers and cache advice. Redirects are reported without following them.
        """
        try:
            result = await resolved_client.call_api_operation(
                service,
                api_version,
                operation_id,
                parameters,
                body,
            )
            payload = result.model_dump(mode="json")
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
                structured_content=payload,
            )
        except UpstreamError as exc:
            payload = exc.to_dict()
        except (GetBibleError, ValueError) as exc:
            payload = {"error": str(exc), "kind": "invalid_request"}
        return CallToolResult(
            is_error=True,
            content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            structured_content=payload,
        )

    @server.tool(title="Find dictionary entry identifiers", annotations=read_only)
    async def search_dictionary_entries(
        dictionary: Annotated[str, Field(min_length=1)],
        query: Annotated[str, Field(min_length=1, max_length=256)],
        match: Literal["exact", "prefix", "contains"] = "exact",
        limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 20,
        offset: Annotated[int, Field(ge=0, strict=True)] = 0,
    ) -> DictionarySearchResult:
        """Find entry IDs by key, alias, search text or ID in a discovered dictionary module.

        Discover modules with dictionaries/v1/listDictionaries first. Fetches the current index
        and filters it locally, returning a bounded page of unchanged records. Key, search and alias
        matching ignores case and combining accents using Unicode NFD; IDs match exactly, including
        case. This is not definition full-text search.
        Exact is the default; use prefix or contains explicitly if needed. Follow next_offset
        with the same inputs. Fetch definitions with dictionaries/v1/getDictionaryEntry and the
        returned exact ID; see_also and backlinks are directed links, not guaranteed synonyms.
        """
        return await resolved_client.search_dictionary_entries(
            dictionary, query, match=match, limit=limit, offset=offset
        )

    @server.tool(title="List GetBible translations", annotations=read_only)
    async def list_translations(api_version: BibleVersion = "v3") -> MappingResult:
        """Discover translation abbreviations, languages, publisher metadata and catalog hashes."""
        return await resolved_client.list_translations(api_version=api_version)

    @server.tool(title="List books in a translation", annotations=read_only)
    async def list_books(
        translation: str = "kjv", api_version: BibleVersion = "v3"
    ) -> MappingResult:
        """Discover book numbers, localized names and hashes in the selected API version."""
        return await resolved_client.list_books(translation, api_version=api_version)

    @server.tool(title="List chapters in a book", annotations=read_only)
    async def list_chapters(
        translation: str,
        book: Annotated[int, Field(ge=1)],
        api_version: BibleVersion = "v3",
    ) -> MappingResult:
        """Return chapter mappings and hashes; discover identifiers before retrieving scripture."""
        return await resolved_client.list_chapters(translation, book, api_version=api_version)

    @server.tool(title="Get complete scripture scope", annotations=read_only)
    async def get_scripture(
        translation: str = "kjv",
        book: Annotated[int | None, Field(ge=1)] = None,
        chapter: Annotated[int | None, Field(ge=1)] = None,
        api_version: BibleVersion = "v3",
    ) -> ScriptureResult:
        """Read a whole chapter, book or translation with before/after .sha consistency checks.

        Omit chapter for a book, omit both for a translation. Native verse data is preserved,
        including v3 tokens and spans. Use query_verses for selected references.
        """
        if chapter is not None and book is None:
            raise ValueError("chapter cannot be supplied without book")
        kind: ScopeKind = (
            "translation" if book is None else "book" if chapter is None else "chapter"
        )
        return await resolved_client.get_scripture(
            ScopeSpec(
                kind=kind,
                translation=translation,
                book=book,
                chapter=chapter,
                api_version=api_version,
            )
        )

    @server.tool(title="Query selected or grouped verses", annotations=read_only)
    async def query_verses(
        references: Annotated[
            str,
            Field(
                min_length=1,
                max_length=512,
                description="Reference, e.g. 'John 3:16-19; 1 John 3:16-19,22'.",
            ),
        ],
        translation: str = "kjv",
        api_version: BibleVersion = "v3",
    ) -> QueryResult:
        """Fetch native reference results without caching or inferred chapter hashes.

        Invalid/unresolved references return errors, never fallback scripture. Translation defaults
        to kjv. Use v3 for richer verse data. TTL metadata is available in source response headers.
        """
        return await resolved_client.query_verses(translation, references, api_version=api_version)

    @server.tool(title="Search Bible text", annotations=read_only)
    async def search_verses(
        search: Annotated[str, Field(min_length=1, max_length=500)],
        translation: str = "kjv",
        api_version: BibleVersion = "v3",
        words: Literal["all", "any", "phrase"] = "all",
        match: Literal["whole_word", "substring"] = "whole_word",
        case_sensitive: bool = False,
        diacritics: Literal["fold", "exact", "insensitive", "sensitive"] = "fold",
        scope: Literal["bible", "old_testament", "new_testament", "deuterocanon"] = "bible",
        book: Annotated[list[str | int] | None, Field(max_length=83)] = None,
        books: str | None = None,
        exclude: Annotated[list[str] | None, Field(max_length=32)] = None,
        proximity: Annotated[int | None, Field(ge=0, le=100)] = None,
        sort: Literal["canonical", "relevance"] = "canonical",
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        offset: Annotated[int, Field(ge=0, le=10000)] = 0,
    ) -> ApiResult:
        """Search text with all native filters and pagination; results are never cached by MCP.

        book/exclude repeat query keys; books is comma-separated. proximity requires words=all.
        A search recognized as a reference may bypass filters. Inspect native pagination metadata.
        Use describe_api_operation for the equivalent read-only JSON POST and aliases.
        """
        parameters: dict[str, Any] = {
            "translation": translation,
            "search": search,
            "words": words,
            "match": match,
            "case_sensitive": case_sensitive,
            "diacritics": diacritics,
            "scope": scope,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        }
        for key, value in {
            "book": book,
            "books": books,
            "exclude": exclude,
            "proximity": proximity,
        }.items():
            if value is not None:
                parameters[key] = value
        return await resolved_client.call_api_operation("search", api_version, "search", parameters)

    @server.tool(title="Get one scope hash", annotations=read_only)
    async def get_hash(
        kind: ScopeKind,
        translation: str,
        book: Annotated[int | None, Field(ge=1)] = None,
        chapter: Annotated[int | None, Field(ge=1)] = None,
        api_version: BibleVersion = "v3",
    ) -> HashResult:
        """Fetch a Bible SHA-1 sidecar. A changed scope invalidates its cached descendants."""
        return await resolved_client.get_hash(
            ScopeSpec(
                kind=kind,
                translation=translation,
                book=book,
                chapter=chapter,
                api_version=api_version,
            )
        )

    @server.tool(title="Get a bulk hash manifest", annotations=read_only)
    async def get_hash_manifest(
        kind: ManifestKind,
        translation: str | None = None,
        book: Annotated[int | None, Field(ge=1)] = None,
        api_version: BibleVersion = "v3",
    ) -> ManifestResult:
        """Return Bible checksums at translation/book/chapter scope for efficient bulk checks."""
        return await resolved_client.get_hash_manifest(
            kind, translation, book, api_version=api_version
        )

    @server.tool(title="Check cached scopes for updates", annotations=read_only)
    async def check_for_updates(
        items: Annotated[list[HashWatch], Field(min_length=1, max_length=100)],
    ) -> UpdateCheckResult:
        """Compare stored Bible hashes, each pinned to its own API version. This does not renew TTL."""
        semaphore = asyncio.Semaphore(resolved_settings.max_parallel_hash_checks)

        async def check(item: HashWatch) -> UpdateItem:
            scope = ScopeSpec(
                kind=item.kind,
                translation=item.translation,
                book=item.book,
                chapter=item.chapter,
                api_version=item.api_version,
            )
            async with semaphore:
                current = await resolved_client.get_hash(scope)
            changed = item.current_hash != current.hash
            action = (
                "Invalidate this scope and all cached descendants; atomically refresh data and hash."
                if changed
                else "Hash unchanged; preserve the original expiry. Refresh expired content before reuse."
            )
            return UpdateItem(
                scope=scope,
                previous_hash=item.current_hash,
                current_hash=current.hash,
                changed=changed,
                required_action=action,
                hash_source_url=current.source.url,
            )

        results = list(await asyncio.gather(*(check(item) for item in items)))
        changed_count = sum(result.changed for result in results)
        return UpdateCheckResult(
            checked_at=datetime.now(UTC),
            changed_count=changed_count,
            unchanged_count=len(results) - changed_count,
            results=results,
            policy=CACHE_POLICY,
        )

    def register_document(uri: str, name: str, content: str, mime: str) -> None:
        @server.resource(uri, name=name, mime_type=mime)
        def document_resource() -> str:
            return content

    for uri, name, content in (
        ("getbible://docs/api", "Complete GetBible integration guide", API_GUIDE),
        ("getbible://docs/cache-policy", "Cache expiry and synchronization", CACHE_GUIDE),
        ("getbible://docs/usage-policy", "Public access and publisher metadata", USAGE_GUIDE),
        ("getbible://docs/study-workflows", "Dictionary and commentary study workflows", STUDY_GUIDE),
    ):
        register_document(uri, name, content, "text/markdown")
    for service, version in CONTRACTS:
        register_document(
            f"getbible://openapi/{service}/{version}",
            f"GetBible {service} {version} OpenAPI",
            json.dumps(registry.document(service, version), ensure_ascii=False),
            "application/json",
        )

    @server.prompt(name="design_getbible_integration", title="Design a GetBible integration")
    def design_getbible_integration(
        application: str,
        caching: str = "Leave query/search uncached; respect upstream TTL and a 30-day maximum elsewhere.",
    ) -> str:
        """Design an integration using discovered API versions, native payloads and correct expiry."""
        return (
            f"Design a GetBible integration for this application:\n{application}\n\n"
            f"Requested caching:\n{caching}\n\n{API_GUIDE}\n{CACHE_GUIDE}\n"
            "Discover exact operations and schemas before writing code. Preserve native payloads "
            "and publisher metadata. Include error handling, pagination, cache keys and expiry."
        )

    @server.custom_route("/healthz", methods=["GET"], name="health")
    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "server": "getbible-mcp",
                "version": __version__,
                "mcp_endpoint": streamable_http_path,
                "api_contracts": len(CONTRACTS),
            }
        )

    async def direct_discovery(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "name": "GetBible MCP",
                "version": __version__,
                "streamable_http": f"{resolved_settings.public_base}{streamable_http_path}",
                "documentation": f"{resolved_settings.public_base}/",
                "stdio": "getbible-mcp --transport stdio",
                "apis": registry.catalog(),
            }
        )

    if streamable_http_path != "/":
        server.custom_route("/", methods=["GET"], name="direct-discovery")(direct_discovery)

    app = server.streamable_http_app(
        streamable_http_path=streamable_http_path,
        json_response=True,
        stateless_http=True,
        host=resolved_settings.bind_host,
        transport_security=security,
    )
    app.router.redirect_slashes = False
    return ServerRuntime(mcp=server, app=app, client=resolved_client, settings=resolved_settings)
