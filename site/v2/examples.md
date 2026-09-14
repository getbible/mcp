# GetBible MCP examples

These JSON objects show tool names and their arguments, not raw JSON-RPC envelopes. An MCP client
initializes the session and calls the tools using the schemas from `tools/list`. Both transports
use the same calls. Examples name versions explicitly so results cannot silently mix v2 and v3.

## Discover services and an exact operation

```json
{"tool": "discover_apis", "arguments": {}}
```

```json
{
  "tool": "describe_api_operation",
  "arguments": {"service": "search", "api_version": "v3"}
}
```

```json
{
  "tool": "describe_api_operation",
  "arguments": {
    "service": "search",
    "api_version": "v3",
    "operation_id": "searchTranslationPost"
  }
}
```

`parameters` uses each described `input_name`. A path/query name collision keeps the plain name for
the path and prefixes the query name with `query.`, such as `translation` and `query.translation`.
Preserve JSON types; repeated URL parameters are supplied as arrays. Pass a POST body separately.

## Discover metadata and read v3 scripture

```json
{"tool": "list_translations", "arguments": {"api_version": "v3"}}
```

```json
{"tool": "list_books", "arguments": {"translation": "kjv", "api_version": "v3"}}
```

```json
{
  "tool": "get_scripture",
  "arguments": {"translation": "kjv", "book": 43, "chapter": 3, "api_version": "v3"}
}
```

Keep the returned native chapter data, including v3 tokens, spans and paragraph markers. The tool
checks the scope SHA-1 before and after the JSON fetch and returns source/cache information.

## Retrieve grouped references

```json
{
  "tool": "query_verses",
  "arguments": {
    "translation": "kjv",
    "references": "John 3:16-19; 1 John 3:16-19,22",
    "api_version": "v3"
  }
}
```

The native chapter-keyed result retains selected verse fields. It has no invented chapter-hash
list, and the MCP marks it non-cacheable. Invalid or missing references return errors; they do not
select a fallback passage. KJV remains the default when the translation is omitted.

## Search with repeated book and exclusion filters

The convenience tool provides typed arguments for the same full-text search:

```json
{
  "tool": "search_verses",
  "arguments": {
    "search": "faith hope",
    "translation": "kjv",
    "api_version": "v3",
    "words": "any",
    "book": [45, 46],
    "sort": "relevance",
    "limit": 25
  }
}
```

The generic tool exposes every operation in the contract, including its URL-parameter form:

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "search",
    "api_version": "v3",
    "operation_id": "searchTranslation",
    "parameters": {
      "translation": "kjv",
      "q": "faith hope",
      "words": "any",
      "book": [45, 46],
      "exclude": ["vain"],
      "sort": "relevance",
      "limit": 25,
      "offset": 0
    }
  }
}
```

Preserve `query`, `results` and `matches`. Read `query.has_more` before requesting the next page;
keep the same filters and increment the offset by the chosen page size.

## Read-only POST search

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "search",
    "api_version": "v3",
    "operation_id": "searchTranslationPost",
    "parameters": {"translation": "kjv"},
    "body": {"q": "faith hope", "words": "all", "proximity": 10, "limit": 25}
  }
}
```

POST performs the same lookup and uses `no-store`. A query-parameter value overrides a body value;
a path value overrides both.

## Discover and read dictionary entries

```json
{
  "tool": "call_api_operation",
  "arguments": {"service": "dictionaries", "api_version": "v1", "operation_id": "listDictionaries"}
}
```

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "dictionaries",
    "api_version": "v1",
    "operation_id": "getDictionaryIndex",
    "parameters": {"dictionary": "strongsgreek"}
  }
}
```

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "dictionaries",
    "api_version": "v1",
    "operation_id": "getDictionaryEntry",
    "parameters": {"dictionary": "strongsgreek", "entry": "G3056"}
  }
}
```

Use IDs from the returned catalog/index for other dictionaries or words. Read module metadata for
provenance and licensing before redistributing definitions.

## Commentary coverage and chapter content

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "commentaries",
    "api_version": "v1",
    "operation_id": "getCommentaryBooks",
    "parameters": {"commentary": "mhc"}
  }
}
```

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "commentaries",
    "api_version": "v1",
    "operation_id": "getCommentaryChapter",
    "parameters": {"commentary": "mhc", "book": 43, "chapter": 3}
  }
}
```

A discovered chapter 0 is the book introduction; retain verse 0 chapter introductions too.

## Public topic bookmarks

```json
{
  "tool": "call_api_operation",
  "arguments": {"service": "bookmarks", "api_version": "v1", "operation_id": "getTopics"}
}
```

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "bookmarks",
    "api_version": "v1",
    "operation_id": "getChapter",
    "parameters": {"book": 43, "chapter": 3}
  }
}
```

Topic data contains coordinates, not scripture text. Read the corresponding chapter or query the
selected verses in the desired translation. These tools do not create or edit personal bookmarks.

## Version-specific checksums and text indexes

```json
{
  "tool": "get_hash",
  "arguments": {"kind": "chapter", "translation": "kjv", "book": 43, "chapter": 3, "api_version": "v3"}
}
```

```json
{
  "tool": "call_api_operation",
  "arguments": {"service": "api", "api_version": "v2", "operation_id": "listTranslationsText"}
}
```

Use returned values when calling `check_for_updates`; a made-up hash is not a valid cache record.
Static checksums do not override the [30-day cache ceiling](cache-policy.md).
