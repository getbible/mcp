# GetBible API V2 public use policy

## Open access

GetBible API V2 is public and open worldwide. It requires no registration, account, API key,
authentication, subscription, payment, or request quota. Applications may call the Main API and
Query API directly. The static API is built for heavy public use and already serves millions of
requests per day.

## Translation copyright information

Each translation's native return data contains the copyright information applicable to that
translation. The catalog at `https://api.getbible.net/v2/translations.json` provides this metadata
for translation discovery. Preserve and honor the returned information when displaying or
redistributing scripture.

GetBible does not add a separate copyright layer to the scripture. The GNU GPL version 2-or-later
license of the GetBible MCP repository applies only to the MCP software and does not relicense
scripture text or override publisher terms.

## Required synchronization agreement

Correct use of the API requires cached scripture to remain synchronized through GetBible hashes.
Every persisted payload must be stored with the hash for its exact translation, book, or chapter
scope. Revalidate at least weekly. If a hash changes, invalidate that scope and its cached
descendants, fetch the current scripture and hash, and replace the stale record atomically.

An integration that does not perform this validation cycle is not complying with the GetBible API
usage agreement because it can continue distributing corrected or outdated scripture text.

See [cache-policy.md](cache-policy.md) for the complete cache procedure.
