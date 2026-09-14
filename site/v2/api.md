# GetBible API integration guide

GetBible MCP exposes scripture, reference lookup and full-text search in v2 and v3, plus dictionaries,
commentaries and public topic bookmarks in v1. Both stdio and Streamable HTTP expose the same tools,
resources and integration prompt. The official public Streamable HTTP endpoint is
[`https://mcp.getbible.net/`](https://mcp.getbible.net/). Use this exact root URL, without appending
`/mcp` or an API version. Another GetBible MCP host may supply its own complete endpoint URL.
Select the upstream version with `api_version`. This is the MCP package 2.0 guide, independent of
upstream API version numbering.

Access is free, with no account or token required by default. Anonymous MCP requests have the same
limits as public search. Honor HTTP 429 and `Retry-After`; use backoff for retries. Contact GetBible
administrators for an optional token for MCP or any API endpoint, and send an issued token securely
through your client's `Authorization: Bearer` header. See the [usage policy](usage-policy.md).

## Discover before calling

1. Call `discover_apis` for the service/version catalog and source OpenAPI URLs.
2. Call `describe_api_operation` with a `service` and `api_version` to list operations; add
   `operation_id` for the exact path/query parameters, request body, response schemas and errors.
3. Call `call_api_operation` with those identifiers and the documented inputs. `parameters` contains
   HTTP parameters and `body` is the optional search POST JSON object.
4. Preserve native upstream data, source URLs and HTTP cache metadata from the tool result.

Tool results wrap native JSON in `data` (or preserve text for text/checksum operations), with source
and cache metadata alongside it. Upstream HTTP errors become failed tool calls. Redirect operations
return their status and `Location` without following the redirect; use canonical versioned operations
when the desired outcome is data.

The complete OpenAPI resources use `getbible://openapi/{service}/{version}`. They are packaged
snapshots of the upstream contracts, available without a live documentation request. Live MCP
`tools/list` is authoritative for the MCP wrapper schemas. An operation ID is scoped to its service
and version: scripture v2 `listTranslations` becomes `getTranslations` in v3, for example.

| Service | Versions | Upstream OpenAPI | Included snapshots |
|---|---|---|---|
| `api` | v2, v3 | [v2](https://api.getbible.net/v2/openapi.json), [v3](https://api.getbible.net/v3/openapi.json) | [v2](../contracts/api-v2.json), [v3](../contracts/api-v3.json) |
| `query` | v2, v3 | [v2](https://query.getbible.net/v2/openapi.json), [v3](https://query.getbible.net/v3/openapi.json) | [v2](../contracts/query-v2.json), [v3](../contracts/query-v3.json) |
| `search` | v2, v3 | [v2](https://search.getbible.net/v2/openapi.json), [v3](https://search.getbible.net/v3/openapi.json) | [v2](../contracts/search-v2.json), [v3](../contracts/search-v3.json) |
| `dictionaries` | v1 | [v1](https://dictionaries.getbible.net/v1/openapi.json) | [v1](../contracts/dictionaries-v1.json) |
| `commentaries` | v1 | [v1](https://commentaries.getbible.net/v1/openapi.json) | [v1](../contracts/commentaries-v1.json) |
| `bookmarks` | v1 | [v1](https://bookmarks.getbible.net/v1/openapi.json) | [v1](../contracts/bookmarks-v1.json) |

The bookmark contract has a relative server URL; resolve it against its upstream document directory,
`https://bookmarks.getbible.net/v1/`, when importing a downloaded copy into other API tools.

## Scripture and translation metadata

Use `list_translations`, `list_books` and `list_chapters` to discover data in a chosen `api_version`.
Use `get_scripture` for a whole translation, book or chapter. Scripture tools default to v3;
pass `"api_version": "v2"` for v2.

| Scope | v2 example | v3 example |
|---|---|---|
| Translation catalog | `https://api.getbible.net/v2/translations.json` | `https://api.getbible.net/v3/translations.json` |
| Translation | `https://api.getbible.net/v2/kjv.json` | `https://api.getbible.net/v3/kjv.json` |
| Book | `https://api.getbible.net/v2/kjv/43.json` | `https://api.getbible.net/v3/kjv/43.json` |
| Chapter | `https://api.getbible.net/v2/kjv/43/3.json` | `https://api.getbible.net/v3/kjv/43/3.json` |

Use the selected translation's mappings to discover valid book numbers and chapter ranges. V3 book
IDs can exceed traditional numbering, including 200; do not impose a shared upper limit from another
API or assume every translation has 66 books. Retrieve copyright,
history and other rich translation metadata once from the translation catalog. Chapter, query and
search results intentionally carry compact translation metadata.

Retain all native fields. V3 can include verse `tokens`, lexical identifiers, morphology, `spans` and
`paragraph` markers, as well as chapter editorial material. Do not flatten v3 into a v2 shape or
invent missing annotations. Span token indexes are zero-based and inclusive; display-word indexes
are one-based and inclusive, with zero meaning unlocated. Read the version's schema before rendering
or linking these structures.

Use `get_hash`, `get_hash_manifest` and `check_for_updates` for scripture SHA-1 values. The generic
operation tool additionally covers catalog/checksum-file hashes and the text indexes published by
v2. Do not infer a v3 text route from a v2 route.

## Reference lookup

`query_verses` resolves selected or grouped references. Example: `John 3:16-19; 1 John 3:16-19,22`.
The canonical URLs are `https://query.getbible.net/v2/kjv/John%203%3A16` and the corresponding `/v3/`
path. Encode the reference as one path segment. Every semicolon-separated group must identify its
book; numeric book references use a space between book and chapter, such as `62 3:16-19`.

Omitting the translation selects KJV. Missing or unresolved references and explicitly unknown
translations return HTTP 404; no request falls back to Matthew 7. Query accepts reference path
parameters, not search filters or arbitrary URL query parameters. The response is keyed by chapter
and retains selected source verse fields. Query does not promise an outer TTL object or chapter
hashes. Use the static API when full chapter editorial content is needed.

## Full-text search

Use `search_verses` for the normal search flow and `call_api_operation` for every documented GET/POST
form. Search POST is read-only. Both methods share the implementation, with precedence: path,
query parameters, JSON body, configured defaults. Prefer canonical versioned routes over aliases.
A reference supplied as search text performs reference lookup and bypasses full-text filters.

| Input | Supported values |
|---|---|
| `q` / path `search` | Search string or reference, 1–500 characters |
| `translation` | Abbreviation; defaults to `kjv` |
| `words` | `all`, `any`, `phrase` |
| `match` | `whole_word`, `substring` |
| `case_sensitive` | Boolean |
| `scope` | `bible`, `old_testament`, `new_testament`, `deuterocanon` |
| `book`, `books` | Repeated `book` values plus comma-separated `books`; at most 83 combined selections |
| `diacritics` | `fold`, `exact`, `insensitive`, `sensitive` |
| `exclude` | Up to 32 terms, each 1–100 characters; repeat `exclude` in GET |
| `proximity` | 0–100 intervening words; requires `words=all` |
| `sort` | `canonical`, `relevance` |
| `limit`, `offset` | Limit 1–100; offset 0–10000 |

Only `book` and `exclude` may repeat as URL query parameters. Inspect the POST body schema for its
additional accepted scalar/array/null forms; do not assume query and JSON types are identical.
Unknown parameters are rejected. Preserve the `{query, results, matches}` envelope. Full-text query
metadata includes total/returned, offset/limit/has_more, criteria and engine/cache information. Use
`has_more` and the documented pagination bounds. Reference results omit full-text-only fields.

## Dictionaries and lexical lookup

Start with `listDictionaries`, then `getDictionaryMetadata` and `getDictionaryIndex` in service
`dictionaries`, version `v1`. The index supplies exact entry IDs; fetch them with
`getDictionaryEntry`. Strong's dictionaries expose tokens such as `G3056` and `H0430`; use the index
instead of guessing padding or constructing a slug from a displayed word. Dictionary entries retain
definitions, links and scripture references. Bulk dictionaries, build information, build reports,
JSON Schemas and the SHA-256 manifest are also available through their documented operations.

## Commentaries and introductions

Start with `listCommentaries`, then `getCommentaryMetadata` and `getCommentaryBooks` in service
`commentaries`, version `v1`. Retrieve a chapter with `getCommentaryChapter`, or use book/whole-module
operations for bulk access. Discover coverage instead of assuming a comment exists for every verse.
Books can range from 1 to 83. Chapter 0 is a book introduction, and verse 0 is a chapter introduction.
A comment is published once at its lowest covered verse; retain its coverage/reference information.
Build records, JSON Schemas and the SHA-256 manifest are available too.

## Public bookmarks and topic names

Service `bookmarks`, version `v1`, is a public topic dataset. `getIndex` describes resource paths;
`getTopics` lists summaries; `getTopic` returns one topic and its verse coordinates. `getBook` and
`getChapter` find topics associated with scripture, while `getLocales` and `getLocale` provide
localized names. Fall back to the English topic name when a translation is missing.

Bookmarks contain references, not scripture text. Resolve coordinates through the selected scripture
API version and translation. `getCatalog`, `getAll` and `getChecksums` support bulk consumers. There
are no HTTP operations for personal bookmark creation, editing or deletion, and no query filtering
or pagination to invent for this static dataset.

## Integration and caching

For a reader, fetch translation metadata and mappings, then only the chapters in view. For a study
application, retain v3 lexical fields and join them to dictionary indexes; discover commentary and
bookmark coverage separately. For search, send filters to the search API, preserve the response
metadata, and retrieve fuller scripture context only when needed.

The MCP performs no persistent result caching. Query/search results are non-cacheable by default.
Their TTL is conveyed by HTTP cache headers, not a guaranteed JSON field. Search `query.sha` is
source translation metadata and is not a checksum of the search response. Follow the full
[cache policy](cache-policy.md): 30 days is the absolute retention ceiling, and shorter upstream
freshness or `no-store` takes precedence. Preserve source/module rights from the catalogs and
metadata documents; see [usage policy](usage-policy.md).
