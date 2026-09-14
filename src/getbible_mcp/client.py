"""Bounded asynchronous access to the read-only GetBible API contracts."""

from __future__ import annotations

import asyncio
import json
import math
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, NoReturn, cast

import httpx

from getbible_mcp.cache import STATIC_CACHE_POLICY, cache_advice
from getbible_mcp.config import Settings
from getbible_mcp.contracts import ContractError, ContractRegistry
from getbible_mcp.models import (
    ApiResult,
    ApiVersion,
    BibleVersion,
    DictionaryMatch,
    DictionarySearchResult,
    HashResult,
    ManifestKind,
    ManifestResult,
    MappingResult,
    QueryResult,
    ScopeSpec,
    ScriptureResult,
    ServiceName,
    SourceInfo,
)

TRANSLATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
CACHE_POLICY = STATIC_CACHE_POLICY
SAFE_RESPONSE_HEADERS = (
    "content-type",
    "cache-control",
    "date",
    "age",
    "expires",
    "etag",
    "last-modified",
    "retry-after",
    "location",
    "vary",
)


class GetBibleError(RuntimeError):
    """Base error exposed through MCP as a failed tool call."""


class InvalidRequestError(GetBibleError):
    """The requested GetBible operation, identifier or scope is invalid."""


class UpstreamError(GetBibleError):
    """An unsuccessful or malformed response with available native error details."""

    def __init__(self, message: str, result: ApiResult | None = None) -> None:
        super().__init__(message)
        self.result = result
        self.status_code = result.source.status_code if result else None
        self.body = result.data if result else None
        self.source = result.source if result else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "result": self.result.model_dump(mode="json") if self.result else None,
        }


class ContentChangedDuringReadError(GetBibleError):
    """The requested content changed repeatedly while being downloaded."""


def _now() -> datetime:
    return datetime.now(UTC)


def _invalid_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Invalid JSON number: {value}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON number exceeds the supported finite range: {value}")
    return parsed


def _translation(value: str) -> str:
    normalized = value.strip().lower()
    if not TRANSLATION_RE.fullmatch(normalized):
        raise InvalidRequestError(
            "translation must be a GetBible abbreviation containing only letters, numbers, '.', "
            "'_' or '-'"
        )
    return normalized


def _bible_version(value: str) -> BibleVersion:
    if value not in {"v2", "v3"}:
        raise InvalidRequestError("api_version must be v2 or v3")
    return cast(BibleVersion, value)


def _dictionary_search_term(value: str) -> str:
    """Define the MCP's matching rule independently of the index builder's algorithm."""
    decomposed = unicodedata.normalize("NFD", value.strip())
    return "".join(
        character for character in decomposed if not unicodedata.category(character).startswith("M")
    ).casefold()


class GetBibleClient:
    """Read-only client with fixed upstreams, bounded responses and native data preservation."""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
        registry: ContractRegistry | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.registry = registry or ContractRegistry()
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

    async def _request(
        self,
        method: str,
        url: str,
        accept: str,
        service: ServiceName,
        version: ApiVersion,
        operation_id: str,
        *,
        params: list[tuple[str, str]] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[bytes, SourceInfo]:
        try:
            # Explicit request options also constrain an injected HTTP client's defaults.
            async with (
                asyncio.timeout(self.settings.request_timeout_seconds),
                self._http.stream(
                    method,
                    url,
                    params=httpx.QueryParams(tuple(params)) if params else None,
                    json=body,
                    headers={"Accept": accept, "User-Agent": self.settings.user_agent},
                    follow_redirects=False,
                    timeout=httpx.Timeout(self.settings.request_timeout_seconds),
                ) as response,
            ):
                source = SourceInfo(
                    url=str(response.url),
                    fetched_at=_now(),
                    api_version=version,
                    service=service,
                    status_code=response.status_code,
                    headers={
                        name: response.headers[name]
                        for name in SAFE_RESPONSE_HEADERS
                        if name in response.headers
                    },
                )
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    if not re.fullmatch(r"[0-9]+", content_length):
                        raise self._response_error(
                            f"GetBible returned an invalid Content-Length for {url}",
                            source,
                            operation_id,
                            method,
                        )
                    declared = content_length.lstrip("0") or "0"
                    if len(declared) > 12 or int(declared) > self.settings.max_response_bytes:
                        raise self._response_error(
                            f"GetBible response exceeds configured size limit: {url}",
                            source,
                            operation_id,
                            method,
                        )
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.settings.max_response_bytes:
                        raise self._response_error(
                            f"GetBible response exceeds configured size limit: {url}",
                            source,
                            operation_id,
                            method,
                        )
                    chunks.append(chunk)
                source.fetched_at = _now()
                return b"".join(chunks), source
        except (httpx.HTTPError, TimeoutError) as exc:
            raise UpstreamError(f"Unable to reach GetBible for {url}: {exc}") from exc

    @staticmethod
    def _result(data: Any, source: SourceInfo, operation_id: str, method: str = "GET") -> ApiResult:
        return ApiResult(
            operation_id=operation_id,
            data=data,
            source=source,
            cache=cache_advice(source, method),
        )

    @classmethod
    def _response_error(
        cls,
        message: str,
        source: SourceInfo,
        operation_id: str,
        method: str = "GET",
        data: Any = None,
    ) -> UpstreamError:
        result = cls._result(data, source, operation_id, method)
        # A malformed successful response is never suitable for reuse either.
        result.cache.cacheable = False
        result.cache.recommended = False
        result.cache.remaining_ttl_seconds = 0
        result.cache.expires_at = source.fetched_at
        result.cache.hash_validation_required = False
        return UpstreamError(message, result=result)

    @classmethod
    def _decode(
        cls,
        raw: bytes,
        source: SourceInfo,
        operation_id: str,
        method: str = "GET",
        *,
        expect_json: bool = False,
    ) -> Any:
        if not raw and source.status_code in {204, 304}:
            return None
        content_type = source.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        json_mime = content_type == "application/json" or content_type.endswith("+json")
        if json_mime or (expect_json and not content_type):
            try:
                return json.loads(
                    raw, parse_constant=_invalid_json_constant, parse_float=_finite_json_float
                )
            except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                raise cls._response_error(
                    f"GetBible returned invalid JSON (HTTP {source.status_code}) for {source.url}",
                    source,
                    operation_id,
                    method,
                    data=raw.decode("utf-8", errors="replace"),
                ) from exc
        if expect_json and 200 <= source.status_code < 300:
            raise cls._response_error(
                f"GetBible returned unexpected Content-Type {content_type!r}; expected JSON "
                f"(HTTP {source.status_code}) for {source.url}",
                source,
                operation_id,
                method,
                data=raw.decode("utf-8", errors="replace"),
            )
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise cls._response_error(
                f"GetBible returned invalid UTF-8 (HTTP {source.status_code}) for {source.url}",
                source,
                operation_id,
                method,
            ) from exc

    @classmethod
    def _check_status(
        cls,
        result: ApiResult,
        method: str = "GET",
        documented_redirects: set[int] | None = None,
    ) -> None:
        status = result.source.status_code
        if 200 <= status < 300 or status in (documented_redirects or set()):
            return
        preview = json.dumps(result.data, ensure_ascii=False)[:2048]
        raise cls._response_error(
            f"GetBible returned HTTP {status} for {result.source.url}: {preview}",
            result.source,
            result.operation_id,
            method,
            data=result.data,
        )

    async def call_api_operation(
        self,
        service: str,
        version: str,
        operation_id: str,
        parameters: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> ApiResult:
        """Execute exactly one validated contract operation without following redirects."""
        try:
            prepared = self.registry.prepare(service, version, operation_id, parameters, body)
            base = self.settings.service_base(prepared.service, prepared.version)
        except (ContractError, ValueError) as exc:
            raise InvalidRequestError(str(exc)) from exc
        # Paths are contract-controlled. Keep any operator-configured deployment prefix.
        version_prefix = f"/{prepared.version}"
        if prepared.path == version_prefix or prepared.path.startswith(f"{version_prefix}/"):
            url = base + prepared.path[len(version_prefix) :]
        else:
            url = base[: -len(version_prefix)] + prepared.path
        if prepared.method.upper() not in {"GET", "POST"}:
            raise InvalidRequestError(
                "Only documented read-only GET and search POST operations run"
            )
        raw, source = await self._request(
            prepared.method,
            url,
            prepared.accept,
            cast(ServiceName, prepared.service),
            cast(ApiVersion, prepared.version),
            operation_id,
            params=prepared.params,
            body=prepared.body,
        )
        expect_json = "application/json" in prepared.accept and "text/plain" not in prepared.accept
        data = self._decode(raw, source, operation_id, prepared.method, expect_json=expect_json)
        result = self._result(data, source, operation_id, prepared.method)
        responses = prepared.operation.get("responses", {})
        redirects = {
            status for status in range(300, 400) if str(status) in responses or "3XX" in responses
        }
        self._check_status(result, prepared.method, redirects)
        return result

    @staticmethod
    def _translation_parameters(translation: str, version: BibleVersion) -> dict[str, Any]:
        name = "abbreviation" if version == "v2" else "translation"
        return {name: _translation(translation)}

    @classmethod
    def _scope_parameters(cls, scope: ScopeSpec) -> dict[str, Any]:
        parameters = cls._translation_parameters(scope.translation, scope.api_version)
        if scope.book is not None:
            parameters["book"] = scope.book
        if scope.chapter is not None:
            parameters["chapter"] = scope.chapter
        return parameters

    async def list_translations(self, api_version: str = "v3") -> MappingResult:
        version = _bible_version(api_version)
        operation = "listTranslations" if version == "v2" else "getTranslations"
        result = await self.call_api_operation("api", version, operation)
        return MappingResult(
            data=result.data, source=result.source, hash_guidance=CACHE_POLICY, cache=result.cache
        )

    async def list_books(self, translation: str, api_version: str = "v3") -> MappingResult:
        version = _bible_version(api_version)
        operation = "listBooks" if version == "v2" else "getBooks"
        result = await self.call_api_operation(
            "api", version, operation, self._translation_parameters(translation, version)
        )
        return MappingResult(
            data=result.data, source=result.source, hash_guidance=CACHE_POLICY, cache=result.cache
        )

    async def list_chapters(
        self, translation: str, book: int, api_version: str = "v3"
    ) -> MappingResult:
        version = _bible_version(api_version)
        operation = "listChapters" if version == "v2" else "getChapters"
        parameters = self._translation_parameters(translation, version)
        parameters["book"] = book
        result = await self.call_api_operation("api", version, operation, parameters)
        return MappingResult(
            data=result.data, source=result.source, hash_guidance=CACHE_POLICY, cache=result.cache
        )

    async def search_dictionary_entries(
        self,
        dictionary: str,
        query: str,
        match: DictionaryMatch = "exact",
        limit: int = 20,
        offset: int = 0,
    ) -> DictionarySearchResult:
        """Search a fresh index locally and return a bounded page in index order.

        Keys, search terms and aliases use Unicode NFD, removal of combining marks,
        and case folding. An exact, case-sensitive entry ID also matches. This is
        MCP-side filtering, not an upstream query endpoint or a definition search.
        """
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise InvalidRequestError("query must be a nonblank string of at most 256 characters")
        query = query.strip()
        normalized_query = _dictionary_search_term(query)
        if not normalized_query:
            raise InvalidRequestError("query must contain a character other than combining marks")
        if not isinstance(match, str) or match not in {"exact", "prefix", "contains"}:
            raise InvalidRequestError("match must be exact, prefix or contains")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidRequestError("limit must be an integer between 1 and 100")
        if type(offset) is not int or offset < 0:
            raise InvalidRequestError("offset must be a nonnegative integer")

        result = await self.call_api_operation(
            "dictionaries", "v1", "getDictionaryIndex", {"dictionary": dictionary}
        )

        def invalid_index() -> UpstreamError:
            return self._response_error(
                "GetBible returned an invalid dictionary index; expected the requested "
                "dictionary and entries with nonempty id, key and search strings",
                result.source,
                result.operation_id,
                data=result.data,
            )

        data = result.data
        if (
            not isinstance(data, dict)
            or data.get("schema") != "getbible-dictionary-index-v1"
            or data.get("dictionary") != dictionary
            or not isinstance(data.get("entries"), list)
        ):
            raise invalid_index()

        selected: list[dict[str, Any]] = []
        total = 0
        for entry in data["entries"]:
            if not isinstance(entry, dict) or any(
                not isinstance(entry.get(name), str) or not entry[name].strip()
                for name in ("id", "key", "search")
            ):
                raise invalid_index()
            aliases = entry.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
                raise invalid_index()
            candidates = [entry["key"], entry["search"], *aliases]
            matched = query == entry["id"]
            for candidate in candidates:
                term = _dictionary_search_term(candidate)
                if (
                    (match == "exact" and term == normalized_query)
                    or (match == "prefix" and term.startswith(normalized_query))
                    or (match == "contains" and normalized_query in term)
                ):
                    matched = True
                    break
            if matched:
                if total >= offset and len(selected) < limit:
                    selected.append(entry)
                total += 1

        next_offset = offset + len(selected)
        return DictionarySearchResult(
            dictionary=dictionary,
            query=query,
            match=match,
            entries=selected,
            total=total,
            count=len(selected),
            offset=offset,
            next_offset=next_offset if next_offset < total else None,
            source=result.source,
            cache=result.cache,
        )

    async def get_hash(self, scope: ScopeSpec) -> HashResult:
        operation = f"get{scope.kind.title()}Checksum"
        result = await self.call_api_operation(
            "api", scope.api_version, operation, self._scope_parameters(scope)
        )
        value = result.data.strip().lower() if isinstance(result.data, str) else ""
        if not SHA_RE.fullmatch(value):
            raise self._response_error(
                f"GetBible returned an invalid SHA value for {result.source.url}",
                result.source,
                operation,
                data=result.data,
            )
        return HashResult(scope=scope, hash=value, source=result.source, cache=result.cache)

    async def get_scripture(self, scope: ScopeSpec) -> ScriptureResult:
        operation = f"get{scope.kind.title()}"
        last_before = ""
        last_after = ""
        for attempt in range(2):
            before = await self.get_hash(scope)
            result = await self.call_api_operation(
                "api", scope.api_version, operation, self._scope_parameters(scope)
            )
            after = await self.get_hash(scope)
            last_before, last_after = before.hash, after.hash
            if last_before == last_after:
                return ScriptureResult(
                    scope=scope,
                    data=result.data,
                    hash=last_after,
                    source=result.source,
                    hash_source_url=after.source.url,
                    consistency_checked=True,
                    consistency_retries=attempt,
                    cache_policy=CACHE_POLICY,
                    cache=result.cache,
                )
        raise ContentChangedDuringReadError(
            f"GetBible content changed repeatedly during retrieval ({last_before} -> {last_after}); "
            "retry the operation"
        )

    async def query_verses(
        self, translation: str, references: str, api_version: str = "v3"
    ) -> QueryResult:
        version = _bible_version(api_version)
        translation = _translation(translation)
        references = references.strip()
        if not references:
            raise InvalidRequestError("references must not be empty")
        result = await self.call_api_operation(
            "query", version, "getScripture", {"translation": translation, "reference": references}
        )
        return QueryResult(
            translation=translation,
            references=references,
            data=result.data,
            source=result.source,
            cache=result.cache,
        )

    async def get_hash_manifest(
        self,
        kind: ManifestKind,
        translation: str | None = None,
        book: int | None = None,
        api_version: str = "v3",
    ) -> ManifestResult:
        version = _bible_version(api_version)
        parameters: dict[str, Any] = {}
        if kind == "all_translations":
            if translation is not None or book is not None:
                raise InvalidRequestError("all_translations manifest takes no translation or book")
            operation = "listTranslationChecksums" if version == "v2" else "getTranslationChecksums"
        elif kind == "translation":
            if translation is None or book is not None:
                raise InvalidRequestError("translation manifest requires translation only")
            translation = _translation(translation)
            parameters = self._translation_parameters(translation, version)
            operation = "listBookChecksums" if version == "v2" else "getBookChecksums"
        elif kind == "book":
            if translation is None or book is None:
                raise InvalidRequestError("book manifest requires translation and book")
            translation = _translation(translation)
            parameters = {**self._translation_parameters(translation, version), "book": book}
            operation = "listChapterChecksums" if version == "v2" else "getChapterChecksums"
        else:
            raise InvalidRequestError("kind must be all_translations, translation or book")
        result = await self.call_api_operation("api", version, operation, parameters)
        return ManifestResult(
            kind=kind,
            translation=translation,
            book=book,
            data=result.data,
            source=result.source,
            cache_policy=CACHE_POLICY,
            cache=result.cache,
        )
