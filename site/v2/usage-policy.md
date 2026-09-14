# GetBible public use policy

## Access

The official public MCP endpoint is [`https://mcp.getbible.net/`](https://mcp.getbible.net/), using
Streamable HTTP at the root URL. Access is free, with no account or token required by default.
The public GetBible scripture, query, search, dictionary, commentary and bookmark endpoints also
support anonymous access. These services are read-only; search POST submits a lookup, not a content
change. Clients connecting to another GetBible MCP host use its complete endpoint URL and access policy.

## Anonymous request limits

The official MCP service uses the same anonymous limits as public search, per client address:

| Limit | Default |
|---|---|
| Request rate | 50 requests per second |
| Burst allowance | 250 requests |
| Nominal hourly budget | 10,000 requests per hour |
| Nominal daily budget | 100,000 requests per day |
| Concurrent connections | 100 per address |

The hourly and daily values are sustained-rate budgets, not hard calendar-hour or calendar-day
quotas. They do not promise a fixed number of requests before rejection or reset at a clock boundary.
Requests must satisfy the applicable limits together.

Handle HTTP 429 by honoring `Retry-After` when present. Back off and reduce concurrency; avoid
immediate retry loops. Applications must also handle other HTTP errors, unavailable upstreams and
the published input/response limits. Each API endpoint's access policy and response headers apply.

## Optional tokens

Contact GetBible administrators to request a token for MCP or any API endpoint. Tokens are optional
for normal public access. Administrators provide the token's scope and applicable access policy;
do not assume one token is valid for every host.

Store an issued token in secure client configuration and send it using the
`Authorization: Bearer <token>` HTTP header. Never place tokens in URLs, tool arguments, source code,
logs or shared examples. A token configured for an MCP connection is a credential for that connection;
it is not a tool parameter or an instruction to forward credentials to upstream services.

## Content rights and provenance

Read the translation catalog for copyright and rich metadata applicable to each translation. V2 and
v3 have separate catalogs. Chapter, query and search results carry compact metadata; absence of
repeated copyright fields does not remove the translation's terms.

Dictionary and commentary catalogs and module metadata carry their own licenses, provenance and
distribution notes. Preserve them alongside displayed or redistributed content. Bookmarks are a
separate topic/reference dataset and contain no scripture text. Respect that dataset's published
license as well as the chosen translation's terms when resolving its references.

GetBible does not add a separate copyright layer to scripture. The GNU GPL version 2-or-later
license of this repository applies to the MCP software and does not relicense translations, study
modules or other upstream datasets.

## Synchronization

The 30-day rotation contract is a condition of cached use. Never retain upstream content beyond
30 days without refreshing, and obey shorter HTTP freshness and `no-store`. Retain the exact
scope/path checksum where published, invalidate changed content and descendants as applicable, and
replace refreshed records atomically. Query/search are not cached by the MCP; their source HTTP
freshness remains relevant to any separate downstream caching implementation.

See [cache-policy.md](cache-policy.md) for the complete procedure.
