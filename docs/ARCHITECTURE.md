# Package architecture

## One library, two transports

The Python package defines MCP tools, documentation resources, complete OpenAPI resources and the
integration-design prompt once. Local stdio and Streamable HTTP use the same server object. The
package is distributed through PyPI; consuming applications own their infrastructure and lifecycle.

Python, JavaScript and PHP clients can connect to an existing remote MCP service without running
language-specific copies of the server. MCP is a JSON-RPC protocol, not a replacement REST API.
Ordinary applications can still use GetBible's HTTP APIs directly.

The host selects the protocol endpoint path: `/` and named paths such as `/mcp` are supported,
independently of upstream API versions. Tool `api_version` chooses
scripture/query/search v2 or v3, or study/bookmark v1. Scripture conveniences default to v3.

## Public library interface

- `getbible_mcp.create_app(settings=None, api_client=None, *, path="/mcp")` returns an ASGI application.
- `getbible_mcp.create_runtime(..., streamable_http_path="/mcp")` returns the application, MCP server,
  HTTP client and resolved settings together.
- `Settings` configures trusted upstreams and request limits; an injected `GetBibleClient` supports
  controlled test transports and application composition.

Importing the public package does not create a default HTTP client or server. Each factory call owns
an independent runtime. The caller must run the ASGI lifespan; a parent mounting the child must
explicitly enter `child.router.lifespan_context(child)`. Lifespan startup initializes MCP resources
and shutdown closes the client's connection pool. Mounting an application without entering its
lifespan is insufficient.

Consuming applications own process management, proxy configuration and public hosting.

## API contract layer

The package includes the complete nine upstream OpenAPI documents under `src/getbible_mcp/openapi/`.
The contract layer merges path-item and operation parameters, retains original parameter locations,
and validates arguments with their advertised JSON Schemas before constructing a request.

`discover_apis` identifies services, versions and source URLs. `describe_api_operation` exposes exact
operation schemas and response contracts. `call_api_operation` executes the declared operation.
Convenience tools cover common scripture, reference and search tasks through the same client.
Search POST is a read-only query operation; the server has no upstream write capability.

Callers choose a known service, version and operation, never an arbitrary URL. Path values are encoded
as segments, parameter types and allowed keys are validated, array serialization follows OpenAPI,
and only declared operations are eligible for a request. Path/query name collisions are exposed as
separate inputs: the plain name selects the path value and `query.<name>` selects the query value.

Upstream defaults are the six public GetBible hosts and their supported version roots. A consuming
application can configure trusted mirrors; MCP callers cannot override hosts. Outbound requests have
timeouts and response-size limits. Redirect operations return their status and `Location` metadata
without following the redirect.

## Payload and error behavior

Native JSON remains intact inside the MCP result, preserving v3 verse tokens, spans, paragraphs,
source metadata and future additional fields. Text indexes and checksums retain text form. Source
metadata records the upstream location, HTTP status and freshness information. Upstream problem
responses remain errors instead of being replaced with fallback scripture.

Query returns selected chapter-keyed verse data without inferred chapter hashes. Search preserves
the `{query, results, matches}` envelope. Reference search and full-text search have different optional
metadata, so clients must not require full-text fields for every result.

## Consistency and freshness

For `get_scripture`, the client reads the scope SHA-1, fetches JSON, and reads the SHA-1 again. If the
hash changes, it retries once; a second mismatch returns an error. This protects against crossing a
static scripture publication boundary.

The library does not cache upstream response data. Query/search results carry `recommended: false`
cache advice; `cacheable` separately reports HTTP eligibility. HTTP freshness is retained for
consumers: 30 days is the hard ceiling, with shorter
`Cache-Control`, `Age`, dates and `Expires` reducing the usable lifetime. `no-store` prohibits
persistence and `no-cache` requires revalidation. Published SHA-1/SHA-256 values do not override
freshness, and search source-translation metadata is not a response checksum.

See [cache policy](../site/v2/cache-policy.md) for downstream synchronization.

## Contract maintenance

OpenAPI snapshots are reviewed package-release inputs. Refresh the packaged and static copies
together using `scripts/refresh_contracts.py --write`, or check upstream drift with `--check`.
Preserve exact source documents and test validation, serialization, transport parity and packaging
before release. Generic tools expose the declared operations without maintaining a separate
hand-written wrapper for every endpoint. All static snapshots are under `site/contracts/`;
`site/v2/` contains MCP package 2.0 documentation for all supported upstream versions.
