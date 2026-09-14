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

Start with the catalog. Choose the requested source and language from its `dictionaries` array;
use the returned `id`, not its display name. These calls demonstrate a Strong's Greek module only
after its catalog record has been discovered. For a complete word-study procedure, including
ambiguous headwords and relationship traversal, read the MCP resource
`getbible://docs/study-workflows` or the [study workflow guide](https://github.com/getbible/mcp/blob/main/docs/STUDY_WORKFLOWS.md).

```json
{
  "tool": "call_api_operation",
  "arguments": {"service": "dictionaries", "api_version": "v1", "operation_id": "listDictionaries"}
}
```

Read the selected module's provenance and content licence:

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "dictionaries",
    "api_version": "v1",
    "operation_id": "getDictionaryMetadata",
    "parameters": {"dictionary": "strongsgreek"}
  }
}
```

```json
{
  "tool": "search_dictionary_entries",
  "arguments": {
    "dictionary": "strongsgreek",
    "query": "G3056",
    "match": "exact",
    "limit": 20,
    "offset": 0
  }
}
```

The helper fetches the index fresh and returns a bounded page of unchanged matching index records.
It searches headwords, IDs and aliases, not definition text. Choose `prefix` or `contains` for a
broader candidate list and follow returned pagination. Pass the matching record's **exact `id`** as `entry`;
`G3056` below is appropriate only if it is the discovered record or an actual source Strong's token.
The same key can have several definitions with distinct `id` and `occurrence` values.

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

Read the definition in `data.text`. Its optional `see_also` and `backlinks` arrays contain outgoing
and incoming links within the same dictionary. Retrieve a linked word using its supplied `id` and
the same `dictionary`, preserving the direction of the relationship. These links do not themselves
assert synonymy or etymology. Use the source texts to explain the relationship, with attribution.
Stop cycles by remembering visited dictionary/id pairs and follow only links relevant to the question.

Pass a scripture citation's `references[].ref` to `query_verses` with the user's translation and
explicit Bible API version. A reference with no `verse` covers a whole chapter; a `verses` array
preserves all cited verses. Do not turn an English word into an assumed Greek/Hebrew lemma.

Integrations needing a full index can call `getDictionaryIndex` through `call_api_operation` with
`service="dictionaries"`, `api_version="v1"` and `parameters={"dictionary":"strongsgreek"}`.
That generic operation returns the entire unpaginated index; never claim a search was exhaustive
after reading a truncated response. Prefer `search_dictionary_entries` for ordinary word lookups.
`search_verses` searches scripture text, and the static dictionary API has no `?q=` search route.

## Commentary coverage and chapter content

Discover the module before selecting its coverage:

```json
{
  "tool": "call_api_operation",
  "arguments": {
    "service": "commentaries",
    "api_version": "v1",
    "operation_id": "listCommentaries"
  }
}
```

The following example uses `mhc` after selecting that returned module. Read
`getCommentaryMetadata` with `{"commentary":"mhc"}` for its author/source, language, licence and
versification, then fetch coverage:

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

Select a `book` and `chapter` actually present in `data.books`. The John 3 example is valid only
when the selected module lists book `43` and chapter `3`.

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

For commentary on verse 16, include every entry where `(entry.verses ?? [entry.verse]).includes(16)`.
A range anchored at verse 14 can include verse 16. Preserve multiple matching entries. A discovered
chapter 0 is the book introduction; retain verse 0 chapter introductions as introductory context.
Cross-chapter comments can appear in both chapter documents: preserve coverage and avoid repeating
the same quotation. Missing coverage should be reported, not replaced with a different passage.

Retrieve the Bible passage separately through `query_verses`; label the commentary as its author's
interpretation and cite the module and returned `source.url`. Its scripture `references` can also
be followed through the query API. The chapter's original fields, ranges and references stay intact.

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
