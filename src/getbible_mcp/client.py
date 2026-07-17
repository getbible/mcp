"""Safe asynchronous client for the static GetBible API V2 endpoints."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from getbible_mcp.config import Settings
from getbible_mcp.models import (
    ChapterHash,
    HashResult,
    ManifestKind,
    ManifestResult,
    MappingResult,
    QueryResult,
    ScopeSpec,
    ScriptureResult,
    SourceInfo,
)

TRANSLATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
REFERENCE_RE = re.compile(r"^(.*\D)(\d+)\s*$")

CACHE_POLICY = (
    "Store the returned hash with cached scripture. Revalidate it at least weekly using the "
    "matching .sha endpoint or checksum manifest. If it changes, invalidate that scope and all "
    "cached descendants, then atomically fetch and store fresh scripture with the new hash. "
    "This synchronization cycle is a condition of the GetBible API usage agreement."
)


class GetBibleError(RuntimeError):
    """Base error exposed through MCP as a failed tool call."""


class InvalidRequestError(GetBibleError):
    """The requested GetBible identifier or scope is invalid."""


class UpstreamError(GetBibleError):
    """The GetBible upstream returned an unsuccessful or malformed response."""


class ContentChangedDuringReadError(GetBibleError):
    """The requested content changed repeatedly while being downloaded."""


def _now() -> datetime:
    return datetime.now(UTC)


def _translation(value: str) -> str:
    normalized = value.strip().lower()
    if not TRANSLATION_RE.fullmatch(normalized):
        raise InvalidRequestError(
            "translation must be a GetBible abbreviation containing only letters, numbers, '.', "
            "'_' or '-'"
        )
    return normalized


def _normalize_book_name(value: str) -> str:
    return "".join(value.casefold().split())


class GetBibleClient:
    """Read-only API client with safe paths, local safeguards, and hash-consistent reads."""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.request_timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": self.settings.user_agent},
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def _read(self, url: str, accept: str) -> tuple[bytes, SourceInfo]:
        try:
            async with self._http.stream("GET", url, headers={"Accept": accept}) as response:
                if response.status_code != 200:
                    preview = bytearray()
                    async for chunk in response.aiter_bytes():
                        preview.extend(chunk[: 500 - len(preview)])
                        if len(preview) >= 500:
                            break
                    body = bytes(preview).decode("utf-8", errors="replace")
                    raise UpstreamError(
                        f"GetBible returned HTTP {response.status_code} for {url}: {body}"
                    )

                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except ValueError as exc:
                        raise UpstreamError(
                            f"GetBible returned an invalid Content-Length for {url}"
                        ) from exc
                    if declared_size > self.settings.max_response_bytes:
                        raise UpstreamError(f"GetBible response exceeds configured size limit: {url}")

                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.settings.max_response_bytes:
                        raise UpstreamError(f"GetBible response exceeds configured size limit: {url}")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Unable to reach GetBible for {url}: {exc}") from exc

        return b"".join(chunks), SourceInfo(url=url, fetched_at=_now())

    async def _json(self, url: str) -> tuple[Any, SourceInfo]:
        raw, source = await self._read(url, "application/json")
        try:
            return json.loads(raw), source
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpstreamError(f"GetBible returned invalid JSON for {url}") from exc

    async def _sha(self, url: str) -> tuple[str, SourceInfo]:
        raw, source = await self._read(url, "text/plain, application/octet-stream;q=0.9")
        try:
            value = raw.decode("ascii").strip().lower()
        except UnicodeDecodeError as exc:
            raise UpstreamError(f"GetBible returned a non-ASCII SHA value for {url}") from exc
        if not SHA_RE.fullmatch(value):
            raise UpstreamError(f"GetBible returned an invalid SHA value for {url}")
        return value, source

    def _scope_paths(self, scope: ScopeSpec) -> tuple[str, str]:
        translation = _translation(scope.translation)
        base = f"/{translation}"
        if scope.kind == "book":
            base += f"/{scope.book}"
        elif scope.kind == "chapter":
            base += f"/{scope.book}/{scope.chapter}"
        return f"{base}.json", f"{base}.sha"

    async def list_translations(self) -> MappingResult:
        url = f"{self.settings.api_base}/translations.json"
        data, source = await self._json(url)
        return MappingResult(data=data, source=source, hash_guidance=CACHE_POLICY)

    async def list_books(self, translation: str) -> MappingResult:
        translation = _translation(translation)
        url = f"{self.settings.api_base}/{translation}/books.json"
        data, source = await self._json(url)
        return MappingResult(data=data, source=source, hash_guidance=CACHE_POLICY)

    async def list_chapters(self, translation: str, book: int) -> MappingResult:
        translation = _translation(translation)
        if not 1 <= book <= 200:
            raise InvalidRequestError("book must be between 1 and 200")
        url = f"{self.settings.api_base}/{translation}/{book}/chapters.json"
        data, source = await self._json(url)
        return MappingResult(data=data, source=source, hash_guidance=CACHE_POLICY)

    async def get_hash(self, scope: ScopeSpec) -> HashResult:
        _, sha_path = self._scope_paths(scope)
        value, source = await self._sha(f"{self.settings.api_base}{sha_path}")
        return HashResult(scope=scope, hash=value, source=source)

    async def get_scripture(self, scope: ScopeSpec) -> ScriptureResult:
        json_path, sha_path = self._scope_paths(scope)
        json_url = f"{self.settings.api_base}{json_path}"
        sha_url = f"{self.settings.api_base}{sha_path}"
        last_before = ""
        last_after = ""

        for attempt in range(2):
            last_before, _ = await self._sha(sha_url)
            data, source = await self._json(json_url)
            last_after, _ = await self._sha(sha_url)
            if last_before == last_after:
                return ScriptureResult(
                    scope=scope,
                    data=data,
                    hash=last_after,
                    source=source,
                    hash_source_url=sha_url,
                    consistency_checked=True,
                    consistency_retries=attempt,
                    cache_policy=CACHE_POLICY,
                )

        raise ContentChangedDuringReadError(
            f"GetBible content changed repeatedly during retrieval ({last_before} -> {last_after}); "
            "retry the operation"
        )

    async def query_verses(self, translation: str, references: str) -> QueryResult:
        translation = _translation(translation)
        references = references.strip()
        if not references or len(references) > 4096:
            raise InvalidRequestError("references must contain between 1 and 4096 characters")

        resolved, unresolved = await self._resolve_reference_scopes(translation, references)
        semaphore = asyncio.Semaphore(self.settings.max_parallel_hash_checks)

        async def fetch_chapter_hash(scope: ScopeSpec) -> ChapterHash:
            async with semaphore:
                result = await self.get_hash(scope)
            return ChapterHash(
                translation=scope.translation,
                book=scope.book or 0,
                chapter=scope.chapter or 0,
                hash=result.hash,
                source_url=result.source.url,
            )

        async def fetch_hashes() -> list[ChapterHash]:
            return list(await asyncio.gather(*(fetch_chapter_hash(scope) for scope in resolved)))

        encoded = quote(references, safe=":;,-")
        url = f"{self.settings.query_base}/{translation}/{encoded}"
        last_before: list[ChapterHash] = []
        last_after: list[ChapterHash] = []

        for attempt in range(2):
            last_before = await fetch_hashes()
            data, source = await self._json(url)
            last_after = await fetch_hashes()
            before_versions = {(item.book, item.chapter): item.hash for item in last_before}
            after_versions = {(item.book, item.chapter): item.hash for item in last_after}
            if before_versions == after_versions:
                cacheable = not unresolved and bool(last_after)
                policy = CACHE_POLICY
                if not cacheable:
                    policy += (
                        " Do not persist this grouped result until every participating chapter has "
                        "been resolved and its hash stored."
                    )
                return QueryResult(
                    translation=translation,
                    references=references,
                    data=data,
                    source=source,
                    chapter_hashes=last_after,
                    unresolved_references=unresolved,
                    cacheable=cacheable,
                    consistency_checked=True,
                    consistency_retries=attempt,
                    cache_policy=policy,
                )

        raise ContentChangedDuringReadError(
            "One or more participating chapters changed repeatedly during the grouped query; "
            "retry the operation"
        )

    async def get_hash_manifest(
        self,
        kind: ManifestKind,
        translation: str | None = None,
        book: int | None = None,
    ) -> ManifestResult:
        if kind == "all_translations":
            if translation is not None or book is not None:
                raise InvalidRequestError("all_translations manifest takes no translation or book")
            path = "/checksum.json"
        elif kind == "translation":
            if translation is None or book is not None:
                raise InvalidRequestError("translation manifest requires translation only")
            translation = _translation(translation)
            path = f"/{translation}/checksum.json"
        else:
            if translation is None or book is None:
                raise InvalidRequestError("book manifest requires translation and book")
            translation = _translation(translation)
            if not 1 <= book <= 200:
                raise InvalidRequestError("book must be between 1 and 200")
            path = f"/{translation}/{book}/checksum.json"

        data, source = await self._json(f"{self.settings.api_base}{path}")
        return ManifestResult(
            kind=kind,
            translation=translation,
            book=book,
            data=data,
            source=source,
            cache_policy=CACHE_POLICY,
        )

    async def _resolve_reference_scopes(
        self,
        translation: str,
        references: str,
    ) -> tuple[list[ScopeSpec], list[str]]:
        own_books = await self.list_books(translation)
        payloads = [own_books.data]
        if translation != "kjv":
            payloads.append((await self.list_books("kjv")).data)

        by_name, valid_numbers = self._book_index(payloads)
        scopes: dict[tuple[int, int], ScopeSpec] = {}
        unresolved: list[str] = []

        for raw_reference in references.split(";"):
            reference = raw_reference.strip()
            left = reference.split(":", 1)[0].strip()
            match = REFERENCE_RE.fullmatch(left)
            if not match:
                unresolved.append(reference)
                continue

            book_token = match.group(1).strip()
            chapter = int(match.group(2))
            if not 1 <= chapter <= 300:
                unresolved.append(reference)
                continue

            book: int | None
            if book_token.isdigit():
                candidate = int(book_token)
                book = candidate if not valid_numbers or candidate in valid_numbers else None
            else:
                book = by_name.get(_normalize_book_name(book_token))

            if book is None:
                unresolved.append(reference)
                continue

            scopes[(book, chapter)] = ScopeSpec(
                kind="chapter",
                translation=translation,
                book=book,
                chapter=chapter,
            )

        return list(scopes.values()), unresolved

    @staticmethod
    def _book_index(payloads: list[Any]) -> tuple[dict[str, int], set[int]]:
        by_name: dict[str, int] = {}
        numbers: set[int] = set()
        number_keys = ("nr", "number", "book_number", "id")
        name_keys = (
            "name",
            "book_name",
            "name_long",
            "title",
            "short_name",
            "abbreviation",
        )

        def visit(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return

            number: int | None = None
            for key in number_keys:
                candidate = value.get(key)
                try:
                    if candidate is not None:
                        number = int(candidate)
                        break
                except (TypeError, ValueError):
                    continue

            if number is not None and 1 <= number <= 200:
                numbers.add(number)
                for key in name_keys:
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        by_name[_normalize_book_name(candidate)] = number

            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child)

        for payload in payloads:
            visit(payload)
        return by_name, numbers
