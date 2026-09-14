# Package configuration and updates

## Configuration boundary

`Settings` supplies the upstream locations and request controls used by each runtime. Default values
point to the public GetBible APIs. `Settings.from_env()` reads the corresponding environment values.
A consuming application may construct settings explicitly or use the environment; MCP tool arguments
cannot change the configured hosts.

| Service/version | Environment variable | Default |
|---|---|---|
| api/v2 | `GETBIBLE_API_V2_BASE` | `https://api.getbible.net/v2` |
| api/v3 | `GETBIBLE_API_V3_BASE` | `https://api.getbible.net/v3` |
| query/v2 | `GETBIBLE_QUERY_V2_BASE` | `https://query.getbible.net/v2` |
| query/v3 | `GETBIBLE_QUERY_V3_BASE` | `https://query.getbible.net/v3` |
| search/v2 | `GETBIBLE_SEARCH_V2_BASE` | `https://search.getbible.net/v2` |
| search/v3 | `GETBIBLE_SEARCH_V3_BASE` | `https://search.getbible.net/v3` |
| dictionaries/v1 | `GETBIBLE_DICTIONARIES_BASE` | `https://dictionaries.getbible.net/v1` |
| commentaries/v1 | `GETBIBLE_COMMENTARIES_BASE` | `https://commentaries.getbible.net/v1` |
| bookmarks/v1 | `GETBIBLE_BOOKMARKS_BASE` | `https://bookmarks.getbible.net/v1` |

Each Bible API/query/search variable identifies its version explicitly. A trusted mirror must
implement the selected contract and include the version suffix in its base URL.

## Request and transport controls

| Environment variable | Meaning | Default |
|---|---|---|
| `GETBIBLE_MCP_REQUEST_TIMEOUT` | Upstream request timeout in seconds | 20 |
| `GETBIBLE_MCP_MAX_RESPONSE_BYTES` | Hard upstream response-size limit | 33,554,432 bytes |
| `GETBIBLE_MCP_MAX_PARALLEL_HASH_CHECKS` | Concurrency for scope update checks | 10 |
| `GETBIBLE_MCP_ALLOWED_HOSTS` | DNS-rebinding Host allowlist | Public GetBible MCP and local test hosts |
| `GETBIBLE_MCP_ALLOWED_ORIGINS` | Allowed Origin values when present | Public GetBible MCP and local test origins |

Choose response limits that fit the consumer's memory and workload. Whole translations and study
modules can be large; chapter and entry operations avoid unnecessary bulk reads. These resource
limits are library protections, not upstream API quotas.

## Lifecycle and diagnostics

Applications using the factory interface must run the returned application's lifespan, including
when embedding it in another ASGI application. The library retains no upstream result cache, session
database or persistent scripture state; shutdown closes its HTTP client.

The stdio transport reserves stdout for MCP messages. Route application logs and diagnostics to
stderr through the MCP host. A healthy MCP process does not guarantee every upstream is available;
clients must handle API timeouts and errors explicitly.

## Package and contract updates

Use a tested `getbible-mcp` package version in the consuming project's dependency management. Update
that dependency through the consuming project's normal validation process; this repository does not
manage API servers, proxies or operating-system services.

For maintainers, `scripts/refresh_contracts.py --check` compares the nine current upstream documents
with the packaged and static snapshots. `--write` refreshes them together. Review the changes and run
`./scripts/check` before releasing a new package. See [publishing](PUBLISHING.md) for PyPI procedures.
