"""Conservative proofs that contract inputs fit the supported wire formats.

JSON Schema validation checks individual values. These checks instead establish
at registry construction that every permitted value has a serializable shape.
Narrowing constraints need not be solved: overestimating permitted values makes
an uncertain contract fail closed, without accepting an unsupported shape.
"""

from __future__ import annotations

import math
import re
from typing import Any

_ALL_TYPES = frozenset({"null", "boolean", "number", "string", "array", "object"})
_SCALAR_TYPES = frozenset({"boolean", "number", "string"})
_MAX_ALTERNATIVES = 64
_MAX_DEPTH = 32


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float) and math.isfinite(value):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise ValueError("Schema literals must contain finite JSON values")


def _reference(document: dict[str, Any], reference: Any) -> Any:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ValueError("Input schemas must use local JSON Schema references")
    target: Any = document
    try:
        for part in reference[2:].split("/"):
            token = part.replace("~1", "/").replace("~0", "~")
            target = target[int(token)] if isinstance(target, list) else target[token]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"Unresolved input schema reference: {reference}") from exc
    return target


def _product(
    left: list[list[dict[str, Any]]], right: list[list[dict[str, Any]]]
) -> list[list[dict[str, Any]]]:
    if len(left) * len(right) > _MAX_ALTERNATIVES:
        raise ValueError("Input schema has too many shape alternatives")
    return [first + second for first in left for second in right]


def _alternatives(
    document: dict[str, Any],
    schema: Any,
    depth: int = 0,
    references: frozenset[str] = frozenset(),
) -> list[list[dict[str, Any]]]:
    """Expand unions into alternatives and intersections into conjunct lists."""
    if depth > _MAX_DEPTH:
        raise ValueError("Input schema exceeds the supported shape depth")
    if schema is False:
        return []
    if schema is True:
        return [[{}]]
    if not isinstance(schema, dict):
        raise ValueError("An input schema must be an object or boolean")
    if "$id" in schema:
        raise ValueError("Scoped input schema identifiers are not supported")
    if "$dynamicRef" in schema or "$recursiveRef" in schema:
        raise ValueError("Dynamic input schema references are not supported")
    base = {
        key: value
        for key, value in schema.items()
        if key not in {"$ref", "allOf", "anyOf", "oneOf"}
    }
    alternatives = [[base]]
    if "$ref" in schema:
        reference = schema["$ref"]
        target = _reference(document, reference)
        if reference in references:
            raise ValueError(f"Circular input shape reference: {reference}")
        alternatives = _product(
            alternatives,
            _alternatives(document, target, depth + 1, references | {reference}),
        )
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword not in schema:
            continue
        branches = schema[keyword]
        if not isinstance(branches, list) or not branches:
            raise ValueError(f"Input schema {keyword} must be a nonempty array")
        if keyword == "allOf":
            for branch in branches:
                alternatives = _product(
                    alternatives, _alternatives(document, branch, depth + 1, references)
                )
        else:
            union: list[list[dict[str, Any]]] = []
            for branch in branches:
                union.extend(_alternatives(document, branch, depth + 1, references))
                if len(union) > _MAX_ALTERNATIVES:
                    raise ValueError("Input schema has too many shape alternatives")
            alternatives = _product(alternatives, union)
    return alternatives


def _types(conjuncts: list[dict[str, Any]]) -> frozenset[str]:
    possible = _ALL_TYPES
    for schema in conjuncts:
        if "type" in schema:
            declared = schema["type"]
            declared = declared if isinstance(declared, list) else [declared]
            if any(not isinstance(item, str) for item in declared):
                raise ValueError("Invalid input schema type")
            normalized = frozenset("number" if item == "integer" else item for item in declared)
            if not normalized or not normalized <= _ALL_TYPES:
                raise ValueError("Invalid input schema type")
            possible &= normalized
        if "const" in schema:
            possible &= {_value_type(schema["const"])}
        if "enum" in schema:
            values = schema["enum"]
            if not isinstance(values, list):
                raise ValueError("Input schema enum must be an array")
            possible &= {_value_type(value) for value in values}
    return possible


def _scalar_conjunction(document: dict[str, Any], schemas: list[Any]) -> None:
    for conjuncts in _alternatives(document, {"allOf": schemas or [True]}):
        if not _types(conjuncts) <= _SCALAR_TYPES:
            raise ValueError("URL parameter members must be typed non-null scalars")


def _literal_shape(value: Any) -> None:
    kind = _value_type(value)
    if kind in _SCALAR_TYPES:
        return
    if kind == "array":
        if all(_value_type(item) in _SCALAR_TYPES for item in value):
            return
    elif kind == "object" and all(
        isinstance(key, str) and _value_type(item) in _SCALAR_TYPES for key, item in value.items()
    ):
        return
    raise ValueError("URL parameters permit only scalars, scalar arrays and flat scalar objects")


def _array_shape(document: dict[str, Any], conjuncts: list[dict[str, Any]]) -> None:
    prefixes = [schema.get("prefixItems", []) for schema in conjuncts]
    if any(not isinstance(prefix, list) for prefix in prefixes):
        raise ValueError("Input schema prefixItems must be an array")
    prefix_count = max((len(prefix) for prefix in prefixes), default=0)
    maximum = min((schema.get("maxItems", math.inf) for schema in conjuncts), default=math.inf)
    # The last representative index covers every item beyond all tuple prefixes.
    for index in range(prefix_count + 1):
        if index >= maximum:
            break
        schemas = [
            prefix[index] if index < len(prefix) else schema.get("items", True)
            for schema, prefix in zip(conjuncts, prefixes, strict=True)
        ]
        _scalar_conjunction(document, schemas)


def _object_shape(document: dict[str, Any], conjuncts: list[dict[str, Any]]) -> None:
    members = [schema.get("properties", {}) for schema in conjuncts]
    patterns = [schema.get("patternProperties", {}) for schema in conjuncts]
    if any(not isinstance(value, dict) for value in [*members, *patterns]):
        raise ValueError("Object input schemas must declare property maps")
    names = {name for properties in members for name in properties}
    for name in names:
        schemas: list[Any] = []
        for schema, properties, expressions in zip(conjuncts, members, patterns, strict=True):
            applicable = [
                value for pattern, value in expressions.items() if re.search(pattern, name)
            ]
            if name in properties:
                applicable.append(properties[name])
            schemas.extend(applicable or [schema.get("additionalProperties", True)])
        _scalar_conjunction(document, schemas)
    # A closed conjunct without patterns excludes all unnamed properties.
    if any(
        schema.get("additionalProperties") is False and not expressions
        for schema, expressions in zip(conjuncts, patterns, strict=True)
    ):
        return
    for expressions in patterns:
        for child in expressions.values():
            _scalar_conjunction(document, [child])
    _scalar_conjunction(
        document, [schema.get("additionalProperties", True) for schema in conjuncts]
    )


def validate_parameter_schema(document: dict[str, Any], schema: Any) -> None:
    """Prove every URL value is a scalar, scalar array or flat scalar object."""
    for conjuncts in _alternatives(document, schema):
        possible = _types(conjuncts)
        if not possible:
            continue
        if "null" in possible:
            raise ValueError("URL parameter schemas must exclude null and untyped values")
        # A finite literal constraint is itself a complete bound on value shape.
        literals: list[Any] | None = None
        for conjunct in conjuncts:
            if "const" in conjunct:
                literals = [conjunct["const"]]
                break
            if "enum" in conjunct:
                literals = conjunct["enum"]
                break
        if literals is not None:
            for literal in literals:
                if _value_type(literal) in possible:
                    _literal_shape(literal)
            continue
        if "array" in possible:
            _array_shape(document, conjuncts)
        if "object" in possible:
            _object_shape(document, conjuncts)


def validate_body_schema(document: dict[str, Any], schema: Any) -> None:
    """Prove a JSON request body has an object root, allowing arbitrary members."""
    possible = frozenset().union(
        *(_types(conjuncts) for conjuncts in _alternatives(document, schema))
    )
    if possible != {"object"}:
        raise ValueError("A JSON request body schema must allow only object roots")
