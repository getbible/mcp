"""Exercise study lookups through MCP using contract-shaped upstream fixtures."""

from __future__ import annotations

from typing import Any

import httpx
from jsonschema import Draft202012Validator
from test_server_http import http_session, structured_result

from getbible_mcp.contracts import ContractRegistry


def validate_document(service: str, schema: str, data: dict[str, Any]) -> None:
    components = ContractRegistry().document(service, "v1")["components"]
    Draft202012Validator(
        {"$ref": f"#/components/schemas/{schema}", "components": components}
    ).validate(data)


async def test_dictionary_discovery_resolves_repeated_keys_links_and_citations() -> None:
    catalog = {
        "schema": "getbible-dictionaries-catalog-v1",
        "version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "base_url": "./",
        "metadata_url_template": "{dictionary}/metadata.json",
        "index_url_template": "{dictionary}/index.json",
        "dictionary_url_template": "{dictionary}.json",
        "entry_url_template": "{dictionary}/{entry}.json",
        "module_count": 1,
        "dictionaries": [
            {
                "id": "strongsgreek",
                "name": "Fixture Greek lexicon",
                "language": "en",
                "license": "Fixture only",
                "entry_count": 3,
                "unique_key_count": 2,
                "strong_prefix": "G",
                "bytes": 2048,
            }
        ],
    }
    index = {
        "schema": "getbible-dictionary-index-v1",
        "dictionary": "strongsgreek",
        "language": "en",
        "name": "Fixture Greek lexicon",
        "entry_url_template": "{entry}.json",
        "entry_count": 3,
        "unique_key_count": 2,
        "entries": [
            {"id": "G3004", "key": "λέγω", "search": "λεγω"},
            {"id": "G3056", "key": "λόγος", "search": "λογος", "aliases": ["logos"]},
            {"id": "G3056--2", "key": "λόγος", "search": "λογος", "occurrence": 2},
        ],
    }
    reference = {
        "text": "John i. 1\u20132",
        "ref": "John 1:1-2",
        "osis": "John.1.1",
        "book": 43,
        "chapter": 1,
        "verse": 1,
        "verses": [1, 2],
    }
    entry = {
        "schema": "getbible-dictionary-entry-v1",
        "dictionary": "strongsgreek",
        "language": "en",
        "id": "G3056--2",
        "key": "λόγος",
        "occurrence": 2,
        "aliases": ["λόγος", "logos"],
        "text": "Second fixture definition; see John i. 1\u20132.",
        "see_also": [{"id": "G3004", "key": "λέγω"}],
        "backlinks": [{"id": "G3056", "key": "λόγος"}],
        "references": [reference],
    }
    linked = {
        "schema": "getbible-dictionary-entry-v1",
        "dictionary": "strongsgreek",
        "language": "en",
        "id": "G3004",
        "key": "λέγω",
        "occurrence": 1,
        "aliases": ["λέγω"],
        "text": "Linked fixture definition.",
        "backlinks": [{"id": "G3056--2", "key": "λόγος"}],
    }
    for schema, payload in (
        ("dictionary-catalog", catalog),
        ("dictionary-index", index),
        ("dictionary-entry", entry),
        ("dictionary-entry", linked),
    ):
        validate_document("dictionaries", schema, payload)
    scripture = {"kjv_43_1": {"verses": [{"verse": 1, "text": "Fixture scripture"}]}}
    documents = {
        "/v1/dictionaries.json": catalog,
        "/v1/strongsgreek/index.json": index,
        "/v1/strongsgreek/G3056--2.json": entry,
        "/v1/strongsgreek/G3004.json": linked,
        "/v3/kjv/John 1:1-2": scripture,
    }
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert not request.url.query
        calls.append(request.url.path)
        host = "query" if request.url.path.startswith("/v3/") else "dictionaries"
        assert request.url.host == f"{host}.getbible.net"
        return httpx.Response(200, json=documents[request.url.path])

    async with http_session(handler) as (session, _):

        async def dictionary(operation: str, **parameters: Any) -> dict[str, Any]:
            result = structured_result(
                await session.call_tool(
                    "call_api_operation",
                    {
                        "service": "dictionaries",
                        "api_version": "v1",
                        "operation_id": operation,
                        "parameters": parameters,
                    },
                )
            )
            assert result["source"]["service"] == "dictionaries"
            assert result["source"]["api_version"] == "v1"
            assert result["source"]["status_code"] == 200
            return result["data"]

        modules = await dictionary("listDictionaries")
        module = modules["dictionaries"][0]["id"]
        received_index = await dictionary("getDictionaryIndex", dictionary=module)
        assert received_index == index
        matches = [record for record in received_index["entries"] if record["search"] == "λογος"]
        assert len(matches) == 2
        alternate = next(record for record in matches if record.get("occurrence", 1) == 2)
        received_entry = await dictionary(
            "getDictionaryEntry", dictionary=module, entry=alternate["id"]
        )
        assert received_entry == entry
        received_link = await dictionary(
            "getDictionaryEntry", dictionary=module, entry=received_entry["see_also"][0]["id"]
        )
        assert received_link == linked
        assert received_link["backlinks"][0]["id"] == received_entry["id"]
        quoted = structured_result(
            await session.call_tool(
                "query_verses",
                {
                    "references": received_entry["references"][0]["ref"],
                    "translation": "kjv",
                    "api_version": "v3",
                },
            )
        )
        assert quoted["data"] == scripture
        assert quoted["cache"]["recommended"] is False
    assert calls == list(documents)


async def test_commentary_coverage_preserves_introductions_ranges_and_extended_books() -> None:
    catalog = {
        "schema": "getbible-commentaries-catalog-v1",
        "version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "base_url": "./",
        "metadata_url_template": "{commentary}/metadata.json",
        "books_url_template": "{commentary}/books.json",
        "commentary_url_template": "{commentary}.json",
        "book_url_template": "{commentary}/{book}.json",
        "chapter_url_template": "{commentary}/{book}/{chapter}.json",
        "module_count": 1,
        "commentaries": [
            {
                "id": "barnes",
                "name": "Fixture commentary",
                "language": "en",
                "license": "Fixture only",
                "book_count": 1,
                "chapter_count": 2,
                "entry_count": 4,
                "bytes": 1024,
            }
        ],
    }
    books = {
        "schema": "getbible-commentary-books-v1",
        "commentary": "barnes",
        "language": "en",
        "name": "Fixture commentary",
        "book_url_template": "{book}.json",
        "chapter_url_template": "{book}/{chapter}.json",
        "book_count": 1,
        "books": [{"book": 83, "name": "Fixture book", "chapters": [0, 3], "entry_count": 4}],
    }
    introduction = {
        "schema": "getbible-commentary-chapter-v1",
        "commentary": "barnes",
        "language": "en",
        "book": 83,
        "name": "Fixture book",
        "chapter": 0,
        "entries": [{"book": 83, "chapter": 0, "verse": 0, "text": "Book introduction"}],
    }
    chapter = {
        **introduction,
        "chapter": 3,
        "entries": [
            {"book": 83, "chapter": 3, "verse": 0, "text": "Chapter introduction"},
            {
                "book": 83,
                "chapter": 3,
                "verse": 14,
                "verses": [14, 15, 16, 17],
                "text": "Comment covering the requested verse within a range.",
                "references": [{"ref": "John 3", "osis": "John.3", "book": 43, "chapter": 3}],
            },
            {"book": 83, "chapter": 3, "verse": 16, "text": "Additional individual comment."},
        ],
    }
    for schema, payload in (
        ("commentary-catalog", catalog),
        ("commentary-books", books),
        ("commentary-chapter", introduction),
        ("commentary-chapter", chapter),
    ):
        validate_document("commentaries", schema, payload)
    documents = {
        "/v1/commentaries.json": catalog,
        "/v1/barnes/books.json": books,
        "/v1/barnes/83/0.json": introduction,
        "/v1/barnes/83/3.json": chapter,
    }
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.host == "commentaries.getbible.net"
        assert not request.url.query
        calls.append(request.url.path)
        return httpx.Response(200, json=documents[request.url.path])

    async with http_session(handler) as (session, _):

        async def commentary(operation: str, **parameters: Any) -> dict[str, Any]:
            return structured_result(
                await session.call_tool(
                    "call_api_operation",
                    {
                        "service": "commentaries",
                        "api_version": "v1",
                        "operation_id": operation,
                        "parameters": parameters,
                    },
                )
            )["data"]

        modules = await commentary("listCommentaries")
        module = modules["commentaries"][0]["id"]
        coverage = await commentary("getCommentaryBooks", commentary=module)
        assert coverage == books
        book = coverage["books"][0]
        received = [
            await commentary(
                "getCommentaryChapter", commentary=module, book=book["book"], chapter=number
            )
            for number in book["chapters"]
        ]
        assert received == [introduction, chapter]
        matches = [
            entry for entry in received[1]["entries"] if 16 in entry.get("verses", [entry["verse"]])
        ]
        assert matches == chapter["entries"][1:]
        assert "verse" not in matches[0]["references"][0]
    assert calls == list(documents)
