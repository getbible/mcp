# GetBible MCP

<!-- mcp-name: net.getbible/mcp -->

[![test](https://github.com/getbible/mcp/actions/workflows/test.yml/badge.svg)](https://github.com/getbible/mcp/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/getbible-mcp.svg)](https://pypi.org/project/getbible-mcp/)
[![License: GPL v2+](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)

Read-only Model Context Protocol access to all nine GetBible API contracts over both standard MCP
transports:

- **Streamable HTTP** at the official endpoint [https://mcp.getbible.net/](https://mcp.getbible.net/), or another host's MCP URL
- **stdio** for developers who install the package and let an AI client launch it locally

Both transports expose exactly the same tools, resources, prompts, validation, and scripture-cache
integrity rules. Scripture tools default to upstream v3; select `api_version: "v2"` explicitly for
upstream v2. Dictionary, commentary and bookmark operations use v1.

## Connect to the official endpoint

**GetBible's official MCP endpoint is [https://mcp.getbible.net/](https://mcp.getbible.net/).**
Add that exact URL to your AI application's remote MCP connections and select **Streamable HTTP**.
The domain root is the protocol endpoint; do not append `/mcp` or an API version.

One connection provides Bible retrieval, reference lookup, full-text search, dictionaries,
commentaries and public bookmarks across all supported API versions. Your client can discover
tools, read the complete API contracts and use the integration-planning prompt. All operations
are read-only; select upstream versions through tool arguments.

Public access is free and needs no account or token. It uses the same default anonymous traffic
limits as GetBible search. Excess traffic receives HTTP `429`; honor `Retry-After` and reduce your
request rate. To request a token for MCP or another GetBible endpoint, contact the GetBible
administrators. See the [access policy](site/v2/usage-policy.md) for limits and
[client guide](docs/CLIENTS.md) for connection and token instructions.

You can also connect to a privately operated instance using the URL supplied by its operator.
The Python library supports configurable endpoint URLs and local stdio clients.

## API coverage

| Service | Versions | Capabilities | Upstream contracts |
|---|---|---|---|
| `api` | v2, v3 | Translation, book and chapter data; catalogs; checksums; v2 text indexes | [v2](https://api.getbible.net/v2/openapi.json), [v3](https://api.getbible.net/v3/openapi.json) |
| `query` | v2, v3 | Resolve individual, ranged and grouped scripture references | [v2](https://query.getbible.net/v2/openapi.json), [v3](https://query.getbible.net/v3/openapi.json) |
| `search` | v2, v3 | Full-text search, filters, ranking, pagination and reference lookup; GET and read-only POST | [v2](https://search.getbible.net/v2/openapi.json), [v3](https://search.getbible.net/v3/openapi.json) |
| `dictionaries` | v1 | Catalogs, metadata, word indexes, definitions, Strong's entries and checksums | [v1](https://dictionaries.getbible.net/v1/openapi.json) |
| `commentaries` | v1 | Catalogs, metadata, book/chapter commentary, introductions and checksums | [v1](https://commentaries.getbible.net/v1/openapi.json) |
| `bookmarks` | v1 | Public topics, verse associations, localized names and checksums | [v1](https://bookmarks.getbible.net/v1/openapi.json) |

The package includes the complete upstream OpenAPI documents. Agents can discover services, inspect
an operation's exact parameters and response schemas, then execute that operation. This covers the
whole API surface without requiring a separate MCP tool for every HTTP route. Native upstream JSON
is preserved, including v3 verse tokens, spans, paragraph markers and additional fields.

## What the two transports mean

| Transport | Who runs the server? | How a client connects | Best use |
|---|---|---|---|
| Streamable HTTP | GetBible or another service operator | `https://mcp.getbible.net/` or the operator's MCP URL | Remote MCP clients |
| stdio | The developer installs this package locally | Client launches `getbible-mcp --transport stdio` | Desktop tools, private environments, local process control |

stdio does not create a public endpoint. The MCP host starts the command as a child process and
exchanges JSON-RPC messages over standard input and output. That local process still reads scripture
from the public GetBible API.

Streamable HTTP connects to a remote MCP service using the same package and tool contract.
The host chooses its endpoint path, including `/` or a named path such as `/mcp`. Use the supplied
URL exactly; upstream API versions remain tool arguments.

## Public API access and translation rights

Public access requires no account or token by default. Traffic limits, HTTP errors and upstream
availability still apply; an integration must handle them instead of assuming every request succeeds.
Administrators issue tokens for approved access to individual endpoints.

Use the translation catalog for copyright and rich translation metadata; query/search and chapter
results carry compact metadata. Preserve and honor each translation's rights, and each study
module's provenance and license. This repository's GPL license applies to the MCP software and does
not relicense upstream content.

Correct API use is conditioned on honoring the hash-validation cycle described below. An
integration that keeps cached scripture without revalidating its hashes is not complying with the
GetBible API usage agreement.

## MCP capabilities

### Tools

| Tool | Purpose |
|---|---|
| `list_translations` | Discover translations, copyright information, metadata, scope, and catalog hashes. |
| `list_books` | Discover numbered and localized book names and hashes. |
| `list_chapters` | Discover chapters and chapter hashes. |
| `get_scripture` | Retrieve a complete translation, book, or chapter with a consistency-checked hash. |
| `query_verses` | Resolve selected/grouped verses, retaining native version-specific data. |
| `search_verses` | Search scripture with the upstream filters and pagination. |
| `get_hash` | Read one translation, book, or chapter `.sha` value. |
| `get_hash_manifest` | Read bulk checksum data for scheduled cache sweeps. |
| `check_for_updates` | Compare stored hashes and receive exact invalidation actions. |
| `discover_apis` | Discover services, supported versions and authoritative contracts. |
| `describe_api_operation` | List operations or inspect exact inputs, outputs and documented errors. |
| `call_api_operation` | Execute any operation in the supported contracts, including text, checksums and read-only search POST. |

All tools are read-only, non-destructive, and idempotent. Scripture tools default to
`api_version: "v3"`; use `"v2"` explicitly for v2 data. Generic operation tools require a service and
version, because operation IDs and parameter names differ across contracts. HTTP POST search is a
read operation and does not change server data.

For `check_for_updates`, specify `api_version` in each watched item so one batch can safely check
several versions.

### Resources

- `getbible://docs/api` — complete integration guide
- `getbible://docs/cache-policy`
- `getbible://docs/usage-policy`
- `getbible://openapi/{service}/{version}` — complete contracts, for example `getbible://openapi/search/v3`

### Prompt

- `design_getbible_integration`

## Mandatory scripture-cache integrity

The MCP server keeps no upstream result cache and recommends using query and search results directly.
A downstream application choosing to cache an eligible response must:

1. Include service, API version and all request inputs in the cache key; retain source HTTP freshness.
2. Never retain data beyond 30 days (2,592,000 seconds); honor shorter HTTP freshness, `Age`, `Expires`,
   `no-cache` and `no-store`. An unchanged hash does not grant an indefinite lifetime.
3. Invalidate the changed scope and every cached descendant.
4. Validate the published checksum where available and fetch replacements into temporary storage.
5. Atomically replace the stale record.

`get_scripture` checks the matching `.sha` value before and after retrieving JSON. If a build changes
mid-request, it retries once instead of returning mismatched data and hash. Scripture `.sha` files
contain SHA-1 values; dictionary, commentary and bookmark manifests use SHA-256. Query results have
no chapter-hash envelope. Search `query.sha` describes the source translation, not the result payload.
Query/search TTL comes from HTTP headers, not a promised JSON field.

See [site/v2/cache-policy.md](site/v2/cache-policy.md).

## Quick local stdio setup

Clone the repository and build an isolated environment:

```bash
git clone https://github.com/getbible/mcp.git getbible-mcp
cd getbible-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps .
```

Configure the MCP client with the absolute executable path:

```json
{
  "mcpServers": {
    "getbible": {
      "command": "/absolute/path/getbible-mcp/.venv/bin/getbible-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

Do not wrap or embed Python inside a shell configuration. The client launches the installed Python
entry point directly.

See [docs/CLIENTS.md](docs/CLIENTS.md) for stdio, remote, and Inspector examples.

Python, JavaScript and PHP applications can connect to the same MCP endpoint using a
compatible client. This project ships one Python server package; npm/Composer server packages are
not required. Ordinary applications can also call the existing REST endpoints directly. The MCP
endpoint uses versioned JSON-RPC discovery and tool requests. The documentation under `site/v2/` describes
MCP package 2.0 and covers every supported upstream API version.

## Python library interface

`getbible_mcp.create_app(settings=None, api_client=None, *, path="/mcp")` returns a standalone ASGI
application. `getbible_mcp.create_runtime(..., streamable_http_path="/mcp")` returns the application,
MCP server, client and settings for consumers needing the individual components. Importing the
package does not create a default client or server.

The factory default is `/mcp`; the host can select `/` or another supported exact path. Clients use
the complete endpoint URL published by that host, without appending an API version or assuming a suffix.

The embedding application owns the ASGI lifespan. If mounting the returned application in a parent,
the parent must enter the child's `app.router.lifespan_context(app)` so MCP startup and HTTP client
cleanup run correctly. See [architecture](docs/ARCHITECTURE.md) for package boundaries and
[configuration](docs/OPERATIONS.md) for settings. API infrastructure setup is outside this package.

## Downloadable packages, TestPyPI, and PyPI

Every successful `test` workflow run builds and smoke-tests one wheel and one source distribution.
GitHub keeps them for 30 days in the run's **Artifacts** section under the name
`python-package-distributions`. This includes runs started manually from **Actions → test → Run
workflow**, so a package can be downloaded and tested without publishing anything.

The separate `publish-testpypi` workflow is manually triggered and publishes validated artifacts to
TestPyPI. Production publishing runs only after a pull request is merged into `main`. GitHub must
confirm that the triggering commit is that PR's final merge commit before the workflow validates
and publishes the package and creates its GitHub tag/release. Open pull requests, direct pushes
and manual dispatch cannot publish to production. Retry an incomplete release by rerunning its
original post-merge workflow; matching existing PyPI files are not uploaded again.

TestPyPI uses Trusted Publishing. Production PyPI reads the project or account token only from the
`PYPI_MCP_TOKEN` GitHub Actions secret in the protected `pypi` environment. See
[docs/PUBLISHING.md](docs/PUBLISHING.md) for the download, TestPyPI, secret setup, and production
release procedures.

`sync-openapi` checks all nine upstream contracts daily and on demand. Changed contracts receive a
coordinated patch-version bump and full validation before the workflow creates or updates one pull
request. Review and merge that PR to release the update automatically. Unchanged contracts do
nothing. The generic tools gain newly described API operations and schemas from the contracts;
unsupported semantics fail validation and require a reviewed implementation change. The workflow
does not auto-merge or rewrite curated convenience tools.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
chmod +x scripts/check
./scripts/check
```

The suite covers all bundled contracts, request validation and serialization, version-preserving
responses, HTTP freshness, hash-consistent reads, MCP schema discovery, both transports, static
documents, CLI behavior and release packaging. Tests use local fixtures and mock HTTP transports.

## Repository layout

```text
src/getbible_mcp/       Python MCP implementation
site/                   Guides and all nine exact OpenAPI snapshots
docs/                   Package architecture, clients, configuration and publishing
tests/                  Unit and protocol integration tests
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Client connections](docs/CLIENTS.md)
- [Package configuration and updates](docs/OPERATIONS.md)
- [Security model](SECURITY.md)
- [Testing](docs/TESTING.md)
- [Publishing to PyPI](docs/PUBLISHING.md)
- [MCP Registry publishing](docs/REGISTRY.md)

## Versioning

Package release 2.0.2 uses the stable official Python MCP SDK 2.2.0 and a host-selected HTTP endpoint.
Package versions and upstream API versions are independent. Scripture tools default to v3; v2
remains fully available through explicit version selection. Never mix upstream v2 and v3 payloads
under one cache key.

The nine packaged contracts and [static snapshots](site/contracts/) are reviewed release inputs.
Use `.venv/bin/python scripts/refresh_contracts.py --check` to check upstream drift, or `--write` to
refresh the packaged and static copies together. Run the full checks before committing an API
contract update. Do not handwrite reduced OpenAPI substitutes. The nine files under `site/contracts/`
are the complete static API catalog.

## License

The GetBible MCP software is licensed under the [GNU General Public License, version 2 or later](LICENSE).
Scripture translations remain governed by the copyright information returned for each translation;
the software license does not relicense scripture content.
