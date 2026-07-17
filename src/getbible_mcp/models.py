"""Strict structured inputs and outputs for MCP tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ScopeKind = Literal["translation", "book", "chapter"]
ManifestKind = Literal["all_translations", "translation", "book"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopeSpec(StrictModel):
    kind: ScopeKind
    translation: str = Field(min_length=1, max_length=64)
    book: int | None = Field(default=None, ge=1, le=200)
    chapter: int | None = Field(default=None, ge=1, le=300)

    @model_validator(mode="after")
    def validate_scope(self) -> ScopeSpec:
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
    api_version: Literal["v2"] = "v2"


class MappingResult(StrictModel):
    data: Any
    source: SourceInfo
    hash_guidance: str


class HashResult(StrictModel):
    scope: ScopeSpec
    hash: str
    source: SourceInfo
    meaning: str = "Opaque content-version token; a change means cached content is stale."


class ScriptureResult(StrictModel):
    scope: ScopeSpec
    data: Any
    hash: str
    source: SourceInfo
    hash_source_url: str
    consistency_checked: bool
    consistency_retries: int
    cache_policy: str


class ChapterHash(StrictModel):
    translation: str
    book: int = Field(ge=1, le=200)
    chapter: int = Field(ge=1, le=300)
    hash: str
    source_url: str


class QueryResult(StrictModel):
    translation: str
    references: str
    data: Any
    source: SourceInfo
    chapter_hashes: list[ChapterHash]
    unresolved_references: list[str]
    cacheable: bool
    consistency_checked: bool
    consistency_retries: int
    cache_policy: str


class ManifestResult(StrictModel):
    kind: ManifestKind
    translation: str | None
    book: int | None
    data: Any
    source: SourceInfo
    cache_policy: str


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
