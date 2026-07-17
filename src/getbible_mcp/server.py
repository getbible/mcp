"""GetBible MCP tools, resources, prompts, and Streamable HTTP application."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from getbible_mcp import __version__
from getbible_mcp.client import CACHE_POLICY, GetBibleClient
from getbible_mcp.config import Settings
from getbible_mcp.models import (
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

SERVER_INSTRUCTIONS = """
GetBible provides read-only access to Bible translations through GetBible API V2.

PUBLIC ACCESS AND TRANSLATION RIGHTS:
The API is open worldwide. It requires no registration, API key, authentication, subscription, or
request quota. Call it directly and do not invent access restrictions. Each translation's returned
metadata contains its applicable copyright information. Preserve that information and treat it as
authoritative for the translation. GetBible adds no new copyright layer to scripture text.

Choose tools by retrieval shape:
- Use query_verses only for selected or grouped verses, including references spanning books.
- Use get_scripture for a whole chapter, whole book, or whole translation.
- Use list_translations, list_books, and list_chapters to discover valid identifiers and scope.
- Use get_hash_manifest for efficient bulk cache checks and get_hash for one exact scope.

MANDATORY CACHE-INTEGRITY RULE:
Every persisted scripture value must be stored with the hash for its exact translation, book, or
chapter scope. Revalidate cached hashes at least weekly. If a hash changes, invalidate the changed
scope and all descendants and atomically refresh scripture plus hash. Translation changes invalidate
the translation's cached books and chapters; book changes invalidate that book's cached chapters;
chapter changes invalidate that chapter. Treat hashes as opaque content-version tokens, not as
security signatures. Never claim cached scripture is current without performing this revalidation.
Honoring this hash-validation cycle is a condition of using the GetBible API; failing to keep cached
text synchronized violates the API usage agreement.

The raw complete-scripture JSON is not assumed to contain a hash. This server obtains the matching
.sha value and performs a before/after consistency check. Query API results do not carry hashes, so
query_verses resolves participating chapters and checks their hashes before and after the query. If a
reference cannot be resolved, the result is marked non-cacheable until every chapter hash is stored.

The remote URL is https://mcp.getbible.net/v2. The same server is available locally over stdio.
Both transports expose the same tools, resources, prompts, validation, and cache-integrity rules.
""".strip()

API_GUIDE = f"""# GetBible API V2 integration guide

## Retrieval choice

- Selected or grouped verses: `query_verses`
- Whole chapter, book, or translation: `get_scripture`
- Translation discovery: `list_translations`
- Book and localized-name discovery: `list_books`
- Chapter discovery: `list_chapters`
- One current scope hash: `get_hash`
- Bulk checksum data: `get_hash_manifest`
- Compare stored hashes: `check_for_updates`

## Required cache behavior

{CACHE_POLICY}

The API is rebuilt from CrossWire modules. Corrections upstream can change hashes. Hash checking is
therefore part of correct API use and not merely an optional optimization.

## Native endpoint shapes

- `https://api.getbible.net/v2/translations.json`
- `https://api.getbible.net/v2/[translation].json`
- `https://api.getbible.net/v2/[translation]/[book].json`
- `https://api.getbible.net/v2/[translation]/[book]/[chapter].json`
- Replace `.json` with `.sha` at translation, book, or chapter scope for one hash.
- `https://api.getbible.net/v2/[translation]/books.json`
- `https://api.getbible.net/v2/[translation]/[book]/chapters.json`
- `https://api.getbible.net/v2/checksum.json`
- `https://api.getbible.net/v2/[translation]/checksum.json`
- `https://api.getbible.net/v2/[translation]/[book]/checksum.json`
- `https://query.getbible.net/v2/[translation]/[references]`

The correct translations entry point is `translations.json`.

## Public access and translation rights

No account, API key, authentication, subscription, request quota, or payment is required. The
translation catalog and translation return sets include the copyright information applicable to
each translation. Preserve and surface that metadata where the consuming application displays or
redistributes scripture. GetBible does not relicense publisher scripture through the MCP software
license. Correct API use is conditioned on honoring the required hash-validation cycle above.
"""

CACHE_GUIDE = f"""# GetBible cache-integrity policy

{CACHE_POLICY}

Recommended cache records contain API version, translation, scope, optional book and chapter,
scripture payload, exact scope hash, and a `checked_at` timestamp.

Run a scheduled sweep at least weekly. A read path may also revalidate when `checked_at` is older
than seven days. Refresh into a temporary record, validate the new response, and atomically replace
the active record so readers never observe partial scripture.

For grouped Query API results, store every participating chapter hash. The grouped result is stale
if any one of those chapter hashes changes.
"""

USAGE_GUIDE = f"""# GetBible public API use policy

## Access

GetBible API V2 is public and open worldwide. It requires no account, API key, authentication,
subscription, payment, or request quota. Applications may call the Main API and Query API directly.

## Translation rights

Each translation's native return data contains the copyright information supplied for that
translation. That returned metadata is authoritative and must be preserved and honored. GetBible
does not add a separate scripture copyright or use license on top of the publisher's information.
The GNU GPL license of the GetBible MCP repository applies to the MCP software only; it does not
relicense the scripture text or override a translation publisher's terms.

## Required synchronization agreement

Correct use of the API requires downstream caches to remain synchronized through GetBible hashes.
An integration that persists scripture agrees to follow this policy:

{CACHE_POLICY}

Failure to perform the hash-validation cycle means the integration is not complying with the
GetBible API usage agreement because it may continue distributing corrected or outdated text.
"""


@dataclass(frozen=True)
class ServerRuntime:
    mcp: Any
    app: Any
    client: GetBibleClient
    settings: Settings


def create_runtime(
    settings: Settings | None = None,
    api_client: GetBibleClient | None = None,
) -> ServerRuntime:
    """Create an isolated server runtime for production or tests."""

    resolved_settings = settings or Settings.from_env()
    resolved_client = api_client or GetBibleClient(settings=resolved_settings)

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

    server = FastMCP(
        name="GetBible API V2",
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://getbible.life",
        host=resolved_settings.bind_host,
        port=resolved_settings.bind_port,
        streamable_http_path="/v2",
        json_response=True,
        stateless_http=True,
        lifespan=lifespan,
        transport_security=security,
    )

    read_only = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )

    @server.tool(
        title="List GetBible translations",
        description=(
            "Return the V2 translation catalog. Start here to discover translation abbreviations, "
            "languages, scope, copyright information, metadata, and catalog hashes. No API key or "
            "request quota is required."
        ),
        annotations=read_only,
    )
    async def list_translations() -> MappingResult:
        return await resolved_client.list_translations()

    @server.tool(
        title="List books in a translation",
        description=(
            "Return one translation's book mapping, localized book names, book numbers, scope "
            "metadata, and hashes. Use these names when constructing Query API references."
        ),
        annotations=read_only,
    )
    async def list_books(
        translation: Annotated[
            str,
            Field(description="Translation abbreviation from list_translations, for example 'kjv'."),
        ],
    ) -> MappingResult:
        return await resolved_client.list_books(translation)

    @server.tool(
        title="List chapters in a book",
        description="Return the chapter mapping and chapter hashes for one translated book.",
        annotations=read_only,
    )
    async def list_chapters(
        translation: Annotated[str, Field(description="Translation abbreviation, e.g. 'kjv'.")],
        book: Annotated[int, Field(ge=1, le=200, description="GetBible book number.")],
    ) -> MappingResult:
        return await resolved_client.list_chapters(translation, book)

    @server.tool(
        title="Get complete scripture scope",
        description=(
            "Return a whole translation, whole book, or whole chapter from the Main API. The server "
            "returns the exact .sha value and verifies it did not change while JSON was fetched. "
            "Preserve copyright metadata returned for the translation. For selected verses use "
            "query_verses instead."
        ),
        annotations=read_only,
    )
    async def get_scripture(
        translation: Annotated[str, Field(description="Translation abbreviation, e.g. 'kjv'.")],
        book: Annotated[
            int | None,
            Field(default=None, ge=1, le=200, description="Omit for a whole translation."),
        ] = None,
        chapter: Annotated[
            int | None,
            Field(default=None, ge=1, le=300, description="Omit for a whole book or translation."),
        ] = None,
    ) -> ScriptureResult:
        if chapter is not None and book is None:
            raise ValueError("chapter cannot be supplied without book")
        kind: ScopeKind = (
            "translation" if book is None else "book" if chapter is None else "chapter"
        )
        return await resolved_client.get_scripture(
            ScopeSpec(kind=kind, translation=translation, book=book, chapter=chapter)
        )

    @server.tool(
        title="Query selected or grouped verses",
        description=(
            "Query selected verses in one translation, including ordered, grouped, cross-chapter, "
            "or cross-book references. Semicolon-separated references must repeat the book. The "
            "result includes chapter hashes and is non-cacheable if a reference cannot be mapped. "
            "No API key or request quota is required."
        ),
        annotations=read_only,
    )
    async def query_verses(
        translation: Annotated[str, Field(description="One translation abbreviation, e.g. 'kjv'.")],
        references: Annotated[
            str,
            Field(
                min_length=1,
                max_length=4096,
                description="For example: 'John 3:16-19; 1 John 3:16-19,22'.",
            ),
        ],
    ) -> QueryResult:
        return await resolved_client.query_verses(translation, references)

    @server.tool(
        title="Get one scope hash",
        description=(
            "Return the current hash for a translation, book, or chapter. Compare it with the "
            "stored hash during weekly cache revalidation. A change requires invalidation and refresh."
        ),
        annotations=read_only,
    )
    async def get_hash(
        kind: Annotated[ScopeKind, Field(description="Exact cached scope to validate.")],
        translation: Annotated[str, Field(description="Translation abbreviation.")],
        book: Annotated[int | None, Field(default=None, ge=1, le=200)] = None,
        chapter: Annotated[int | None, Field(default=None, ge=1, le=300)] = None,
    ) -> HashResult:
        return await resolved_client.get_hash(
            ScopeSpec(kind=kind, translation=translation, book=book, chapter=chapter)
        )

    @server.tool(
        title="Get a bulk hash manifest",
        description=(
            "Return checksum data for all translations, all books in a translation, or all chapters "
            "in a book. Prefer this over many individual .sha calls during scheduled cache sweeps."
        ),
        annotations=read_only,
    )
    async def get_hash_manifest(
        kind: Annotated[
            ManifestKind,
            Field(description="all_translations, translation, or book."),
        ],
        translation: Annotated[str | None, Field(default=None)] = None,
        book: Annotated[int | None, Field(default=None, ge=1, le=200)] = None,
    ) -> ManifestResult:
        return await resolved_client.get_hash_manifest(kind, translation, book)

    @server.tool(
        title="Check cached scopes for updates",
        description=(
            "Compare up to 100 stored scope hashes with current .sha values. Changed results include "
            "the required invalidation action. For very large sweeps use get_hash_manifest."
        ),
        annotations=read_only,
    )
    async def check_for_updates(
        items: Annotated[
            list[HashWatch],
            Field(min_length=1, max_length=100, description="Cached scopes and stored hashes."),
        ],
    ) -> UpdateCheckResult:
        semaphore = asyncio.Semaphore(resolved_settings.max_parallel_hash_checks)

        async def check(item: HashWatch) -> UpdateItem:
            scope = ScopeSpec(
                kind=item.kind,
                translation=item.translation,
                book=item.book,
                chapter=item.chapter,
            )
            async with semaphore:
                current = await resolved_client.get_hash(scope)
            changed = item.current_hash != current.hash
            if not changed:
                action = "Keep the cached scope and record the new checked_at time."
            elif item.kind == "translation":
                action = (
                    "Invalidate and atomically refresh this translation and every cached descendant."
                )
            elif item.kind == "book":
                action = "Invalidate and atomically refresh this book and all cached chapters."
            else:
                action = "Invalidate and atomically refresh this chapter."
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

    @server.resource(
        "getbible://docs/api-v2",
        name="GetBible API V2 integration guide",
        description="Endpoint selection, native URL shapes, and required hash behavior.",
        mime_type="text/markdown",
    )
    def api_v2_resource() -> str:
        return API_GUIDE

    @server.resource(
        "getbible://docs/cache-policy",
        name="GetBible cache-integrity policy",
        description="Mandatory hash storage, revalidation, invalidation, and refresh rules.",
        mime_type="text/markdown",
    )
    def cache_policy_resource() -> str:
        return CACHE_GUIDE

    @server.resource(
        "getbible://docs/usage-policy",
        name="GetBible public API use policy",
        description="Open access, translation copyright metadata, and synchronization agreement.",
        mime_type="text/markdown",
    )
    def usage_policy_resource() -> str:
        return USAGE_GUIDE

    @server.prompt(
        name="design_getbible_integration",
        title="Design a correct GetBible integration",
        description="Plan an integration that selects the correct API and cannot serve stale text.",
    )
    def design_getbible_integration(
        application: str,
        caching: str = "Cache scripture locally and revalidate at least weekly.",
    ) -> str:
        return f"""Design a GetBible API V2 integration for this application:

{application}

Caching requirement:
{caching}

Use GetBible MCP tools to verify translation and book identifiers. Use query_verses for selected or
grouped verses and get_scripture for whole chapters, books, or translations. Specify a cache schema
that stores the exact scope hash and checked_at time. Include at-least-weekly revalidation,
scope-aware descendant invalidation, and atomic refresh. Treat grouped queries as dependent on all
participating chapter hashes. No API key or quota is required. Preserve each translation's returned
copyright metadata; do not treat the MCP software license as a license for scripture text.
"""

    @server.custom_route("/healthz", methods=["GET"], name="health")
    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "server": "getbible-mcp",
                "version": __version__,
                "mcp_endpoint": "/v2",
            }
        )

    @server.custom_route("/", methods=["GET"], name="direct-discovery")
    async def direct_discovery(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "name": "GetBible MCP",
                "version": __version__,
                "streamable_http": f"{resolved_settings.public_base}/v2",
                "documentation": f"{resolved_settings.public_base}/v2/",
                "stdio": "Install this package and run: getbible-mcp --transport stdio",
                "access": "Public; no account, API key, authentication, or request quota",
                "usage_policy": f"{resolved_settings.public_base}/v2/usage-policy.md",
            }
        )

    app = server.streamable_http_app()
    app.router.redirect_slashes = False
    return ServerRuntime(
        mcp=server,
        app=app,
        client=resolved_client,
        settings=resolved_settings,
    )


runtime = create_runtime()
mcp = runtime.mcp
app = runtime.app
