from __future__ import annotations

import pytest
from pydantic import ValidationError

from getbible_mcp.models import ScopeSpec


@pytest.mark.parametrize(
    "scope",
    [
        {"kind": "translation", "translation": "kjv", "book": 1},
        {"kind": "book", "translation": "kjv"},
        {"kind": "book", "translation": "kjv", "book": 1, "chapter": 1},
        {"kind": "chapter", "translation": "kjv", "book": 1},
    ],
)
def test_invalid_scope_combinations_are_rejected(scope: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScopeSpec.model_validate(scope)


def test_valid_chapter_scope() -> None:
    scope = ScopeSpec(kind="chapter", translation="kjv", book=66, chapter=1)
    assert scope.book == 66
    assert scope.chapter == 1
    assert scope.api_version == "v3"


def test_scope_supports_extended_v3_book_ids_and_explicit_v2_limits() -> None:
    scope = ScopeSpec(kind="chapter", translation="kjv", book=1000000, chapter=1)
    assert scope.api_version == "v3"
    with pytest.raises(ValidationError, match="V2 book numbers"):
        ScopeSpec(kind="chapter", translation="kjv", book=1000000, chapter=1, api_version="v2")
