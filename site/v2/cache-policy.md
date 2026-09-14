# GetBible cache policy

The MCP keeps no upstream result cache and recommends using query and search data directly.
A downstream application choosing to cache an eligible response must remain within GetBible's 30-day
rotation contract and obey any shorter upstream HTTP freshness.

## Freshness and the 30-day ceiling

- Never retain a response beyond 30 days (2,592,000 seconds) without refreshing it against the source.
  An unchanged content hash does not extend an old response indefinitely.
- Use the remaining lifetime in `Cache-Control`, accounting for `Age` and response dates. Respect
  `Expires` when applicable. Do not reset a response's remaining lifetime to 30 days when receiving it
  from an intermediary.
- `no-store` prohibits persistence. `no-cache` requires revalidation before reuse. Missing usable
  freshness is not permission to invent a long-lived cache.
- A shorter TTL wins. Do not use `stale-while-revalidate` or an error fallback to cross the hard
  30-day ceiling. If refresh fails after expiry, report unavailable data rather than claiming it is
  current.
- Include service, API version, operation and every effective request input in the cache key. Never
  share entries across v2/v3, translations, reference groups, search filters or pagination offsets.

## Scripture checksums

Static scripture v2/v3 publish SHA-1 `.sha` values for translations, books, chapters and indexes.
Store the hash for the exact scope with its content. `get_scripture` reads the scope hash before and
after the JSON fetch and retries once if publication changes mid-read.

When a translation hash changes, invalidate its cached translation, books and chapters. A changed
book hash invalidates that book and its chapters; a changed chapter hash invalidates that chapter.
Fetch replacement data and the matching current hash into temporary storage, then atomically swap
the record. Retain the source response time and expiration; do not mark an unsuccessful check as
successful. Bulk checksum manifests support scheduled validation before entries expire.

Hash checking is a synchronization mechanism. It is not a cryptographic proof of publisher identity
and does not replace HTTP freshness or the retention ceiling.

## Dictionary, commentary and bookmark checksums

Dictionary and commentary `hashes.json` files contain SHA-256 values keyed by document path.
Bookmarks use `checksums.json`, also with SHA-256. These are separate contracts from scripture
SHA-1 `.sha` files. Preserve their declared algorithm and exact path identity. Compare the matching
file digest when replacing or reusing a cached document, while applying the same retention ceiling
and source freshness.

## Query and search

Query responses have no published chapter-hash envelope. Search responses can contain `query.sha`
and `query.cache`; these describe the source translation and engine state, not the hash or TTL of
the returned result. Do not manufacture a checksum from those fields.

Live query/search GET responses convey the remaining source lifetime through HTTP `Cache-Control`,
with an ETag for conditional requests. TTL is not promised in JSON. Search POST responses use
`no-store`. The MCP preserves source HTTP metadata and sets `recommended: false` for runtime caching;
`cacheable` separately reports whether HTTP permits reuse. An integration that explicitly caches
eligible GET results must honor that metadata,
conditional revalidation rules and the 30-day maximum. A 304 is useful only with the corresponding
stored representation; never interpret an empty response as fresh scripture.
