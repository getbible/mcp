# Mandatory GetBible cache-integrity policy

GetBible scripture builds follow CrossWire modules. A correction upstream can change a translation,
book, or chapter in a later build. Applications may cache scripture for performance, but every cache
entry must retain its exact scope hash and the time that hash was last checked.

This synchronization cycle is a condition of the GetBible API usage agreement, not an optional
performance recommendation.

## Required rules

1. Store scripture with the hash for the exact translation, book, or chapter payload cached.
2. Revalidate the hash at least weekly, even if the application's ordinary cache TTL is longer.
3. A changed translation hash invalidates the translation and every cached book and chapter below it.
4. A changed book hash invalidates the book and every cached chapter below it.
5. A changed chapter hash invalidates that chapter.
6. Fetch replacement JSON and hash into temporary storage and atomically replace the active record.
7. If hash validation fails, do not advance `checked_at` or claim that cached text is current.

Recommended record:

```json
{
  "api_version": "v2",
  "translation": "kjv",
  "scope": "chapter",
  "book": 66,
  "chapter": 1,
  "payload": {},
  "hash": "40-character-upstream-value",
  "checked_at": "2026-07-15T10:00:00Z"
}
```

For grouped Query API results, store every participating chapter hash. If any chapter hash changes,
evict or rebuild the grouped result.

Treat hashes as opaque equality tokens. They indicate a content-version change; they are not proof
of publisher identity and are not a cryptographic trust mechanism.
