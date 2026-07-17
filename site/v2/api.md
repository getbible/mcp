# GetBible API V2

## Access and translation rights

The API is public and requires no registration, API key, authentication, subscription, payment, or
request quota. Call the endpoints directly. The translation catalog and translation return sets
carry the copyright information applicable to each translation. Preserve and honor that metadata.
GetBible adds no separate scripture copyright. See [usage-policy.md](usage-policy.md).

## Main API

Use the Main API for complete scopes:

```text
https://api.getbible.net/v2/[translation].json
https://api.getbible.net/v2/[translation]/[book_number].json
https://api.getbible.net/v2/[translation]/[book_number]/[chapter_number].json
```

Examples:

```text
https://api.getbible.net/v2/kjv.json
https://api.getbible.net/v2/kjv/1.json
https://api.getbible.net/v2/kjv/1/1.json
```

Use the mapping helpers to discover valid data:

```text
https://api.getbible.net/v2/translations.json
https://api.getbible.net/v2/kjv/books.json
https://api.getbible.net/v2/kjv/66/chapters.json
```

The correct catalog filename is `translations.json`. Never guess book numbering; discover it from
the selected translation's book mapping.

## Query API

Use the Query API for selected or grouped verses in one translation:

```text
https://query.getbible.net/v2/[translation]/[references]
```

Examples before URL encoding:

```text
John 3:16
John 3:16-19; 1 John 3:16-19,22
John 3:6; Genesis 1:27; John 1:3,2
```

Every semicolon-separated reference must include its book name or number. Returned verses preserve
query order, including explicitly reordered verses within a chapter. Names from the translation's
`books.json` mapping are valid; KJV names are accepted as defaults across translations. Numeric book
references require a space between book and chapter, for example `62 3:16-19`.

Do not use the Query API for a complete chapter or book. Do not use the Main API for a sparse verse
selection.

## Hashes and mappings

Replace `.json` with `.sha` to obtain one exact scope hash:

```text
https://api.getbible.net/v2/kjv.sha
https://api.getbible.net/v2/kjv/66.sha
https://api.getbible.net/v2/kjv/66/1.sha
```

Bulk checksum manifests:

```text
https://api.getbible.net/v2/checksum.json
https://api.getbible.net/v2/kjv/checksum.json
https://api.getbible.net/v2/kjv/66/checksum.json
```

See [cache-policy.md](cache-policy.md) for mandatory downstream behavior.
The hash-validation cycle is a condition of the GetBible API usage agreement.
