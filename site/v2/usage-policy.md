# GetBible public use policy

## Access

The public GetBible scripture, query, search, dictionary, commentary and bookmark endpoints are
read-only and require no account or API key. The supplied MCP service adds no authentication,
subscription or per-address request quota. Applications must still handle HTTP errors, unavailable
upstreams and the published input/response limits. Read-only search POST submits a lookup, not a
content change.

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
