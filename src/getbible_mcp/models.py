"""Strict structured inputs and outputs for MCP tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ScopeKind = Literal["translation", "book", "chapter"]
ManifestKind = Literal["all_translations", "translation", "book"]
BibleVersion = Literal["v2", "v3"]
ApiVersion = Literal["v1", "v2", "v3"]
ServiceName = Literal["api", "query", "search", "dictionaries", "commentaries", "bookmarks"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopeSpec(StrictModel):
    kind: ScopeKind
    translation: str = Field(min_length=1, max_length=64)
    api_version: BibleVersion = "v3"
    book: int | None = Field(default=None, ge=1, le=281474977710655)
    chapter: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_scope(self) -> ScopeSpec:
        if self.api_version == "v2" and self.book is not None and self.book > 89:
            raise ValueError("V2 book numbers must be between 1 and 89")
        if self.kind == "translation" and (self.book is not None or self.chapter is not None):
            raise ValueError("translation scope must not include book or chapter")
        if self.kind == "book" and (self.book is None or self.chapter is not None):
            raise ValueError("book scope requires book and must not include chapter")
        if self.kind == "chapter" and (self.book is None or self.chapter is None):
            raise ValueError("chapter scope requires book and chapter")
        return self


class HashWatch(ScopeSpec):
    current_hash: str = Field(min_length=1, max_length=128)

    @field_validator("current_hash")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        return value.strip().lower()


class SourceInfo(StrictModel):
    url: str
    fetched_at: datetime
    api_version: ApiVersion
    service: ServiceName
    status_code: int = Field(default=200, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)


class CacheAdvice(StrictModel):
    """Consumer guidance only: this MCP never stores upstream responses."""

    cacheable: bool
    recommended: bool
    max_retention_seconds: int = 30 * 24 * 60 * 60
    remaining_ttl_seconds: int = Field(ge=0)
    expires_at: datetime
    hash_validation_required: bool
    policy: str


class ApiResult(StrictModel):
    """Native upstream data with provenance and a separate cache contract."""

    operation_id: str
    data: Any
    source: SourceInfo
    cache: CacheAdvice


class MappingResult(StrictModel):
    data: Any
    source: SourceInfo
    hash_guidance: str
    cache: CacheAdvice | None = None


class HashResult(StrictModel):
    scope: ScopeSpec
    hash: str
    source: SourceInfo
    cache: CacheAdvice | None = None
    meaning: str = (
        "Published SHA-1 checksum and version token; a change means cached content is stale. "
        "Reading the token does not itself verify downloaded scripture bytes."
    )


class ScriptureResult(StrictModel):
    scope: ScopeSpec
    data: Any
    hash: str
    source: SourceInfo
    hash_source_url: str
    consistency_checked: bool
    consistency_retries: int
    cache_policy: str
    cache: CacheAdvice | None = None


class QueryResult(StrictModel):
    translation: str
    references: str
    data: Any
    source: SourceInfo
    cache: CacheAdvice


class ManifestResult(StrictModel):
    kind: ManifestKind
    translation: str | None
    book: int | None
    data: Any
    source: SourceInfo
    cache_policy: str
    cache: CacheAdvice | None = None


class UpdateItem(StrictModel):
    scope: ScopeSpec
    previous_hash: str
    current_hash: str
    changed: bool
    required_action: str
    hash_source_url: str


class UpdateCheckResult(StrictModel):
    checked_at: datetime
    changed_count: int
    unchanged_count: int
    results: list[UpdateItem]
    policy: str
