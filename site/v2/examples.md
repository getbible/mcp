# GetBible MCP examples

The examples below describe tool arguments. MCP clients obtain the authoritative schemas from the
live server.

## Discover a translation and its books

```json
{"tool": "list_translations", "arguments": {}}
```

```json
{"tool": "list_books", "arguments": {"translation": "kjv"}}
```

## Retrieve one chapter

```json
{
  "tool": "get_scripture",
  "arguments": {"translation": "kjv", "book": 43, "chapter": 3}
}
```

The result contains the chapter JSON, its `.sha` value, the source URLs, and the required cache
policy. The server checks the SHA before and after downloading the JSON.

## Retrieve grouped verses

```json
{
  "tool": "query_verses",
  "arguments": {
    "translation": "kjv",
    "references": "John 3:16-19; 1 John 3:16-19,22"
  }
}
```

The result contains every participating chapter hash and verifies those hashes before and after the
query. It is marked non-cacheable when a reference cannot be mapped to a translated book and chapter.

## Check one cached chapter

```json
{
  "tool": "get_hash",
  "arguments": {"kind": "chapter", "translation": "kjv", "book": 66, "chapter": 1}
}
```

## Check several cached scopes

```json
{
  "tool": "check_for_updates",
  "arguments": {
    "items": [
      {"kind": "translation", "translation": "kjv", "current_hash": "stored-value"},
      {"kind": "chapter", "translation": "kjv", "book": 66, "chapter": 1, "current_hash": "stored-value"}
    ]
  }
}
```
