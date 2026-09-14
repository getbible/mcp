"""Reviewed OpenAPI contracts and safe, schema-validated request preparation.

The packaged upstream documents are the source of operation names, parameter
constraints and response descriptions. No network access occurs during discovery
or validation, and callers cannot supply an HTTP method or destination URL.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

CONTRACT_URLS = {
    (service, version): f"https://{host}.getbible.net/{version}/openapi.json"
    for service, host, versions in (
        ("api", "api", ("v2", "v3")),
        ("query", "query", ("v2", "v3")),
        ("search", "search", ("v2", "v3")),
        ("dictionaries", "dictionaries", ("v1",)),
        ("commentaries", "commentaries", ("v1",)),
        ("bookmarks", "bookmarks", ("v1",)),
    )
    for version in versions
}

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")


class ContractError(ValueError):
    """An unknown operation, invalid input or unsupported contract shape."""


@dataclass(frozen=True)
class PreparedRequest:
    """A request restricted to a published operation on a configured service."""

    service: str
    version: str
    operation_id: str
    method: str
    path: str
    params: list[tuple[str, str]]
    body: dict[str, Any] | None
    accept: str
    operation: dict[str, Any]


@dataclass(frozen=True)
class _Operation:
    method: str
    path: str
    operation: dict[str, Any]
    parameters: dict[str, dict[str, Any]]
    input_schema: dict[str, Any]
    accept: str


def _resolve(document: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """Resolve local Reference Objects, retaining any sibling annotations."""
    visited: set[str] = set()
    while "$ref" in value:
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ContractError("Contracts must use local references")
        if reference in visited:
            raise ContractError(f"Circular Reference Object: {reference}")
        visited.add(reference)
        target: Any = document
        try:
            for part in reference[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError) as exc:
            raise ContractError(f"Unresolved contract reference: {reference}") from exc
        if not isinstance(target, dict):
            raise ContractError(f"Contract reference is not an object: {reference}")
        value = {**target, **{key: item for key, item in value.items() if key != "$ref"}}
    return value


def _check_references(value: Any) -> None:
    """Never permit JSON Schema validation to fetch an external reference."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef"} and (
                not isinstance(item, str) or not item.startswith("#/")
            ):
                raise ContractError("Contracts must use local JSON Schema references")
            _check_references(item)
    elif isinstance(value, list):
        for item in value:
            _check_references(item)


def _server_prefix(document: dict[str, Any], source_url: str) -> str:
    """Resolve both version-relative servers and origin-relative path documents."""
    servers = document.get("servers", [{"url": "/"}])
    if len(servers) != 1 or not isinstance(servers[0].get("url"), str):
        raise ContractError("A contract must define a single unambiguous server")
    server: str = servers[0]["url"]
    if "{" in server or "}" in server:
        raise ContractError("Templated contract servers are not supported")
    resolved = urlsplit(urljoin(source_url, server))
    source = urlsplit(source_url)
    if (
        resolved.scheme != "https"
        or resolved.netloc != source.netloc
        or resolved.query
        or resolved.fragment
    ):
        raise ContractError("A contract server must use its documented GetBible origin")
    return resolved.path.rstrip("/")


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return str(int(value)) if value.is_integer() else str(value)
    raise ContractError("URL parameter values must be finite numbers, strings or booleans")


def _path_value(value: Any, name: str) -> str:
    text = _scalar(value)
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        raise ContractError(f"Path parameter {name!r} must be one nonempty, safe path segment")
    return quote(text, safe="")


def _query_values(parameter: dict[str, Any], value: Any) -> list[tuple[str, str]]:
    name = parameter["name"]
    if isinstance(value, list):
        values = [_scalar(item) for item in value]
        if parameter.get("explode", True):
            return [(name, item) for item in values]
        return [(name, ",".join(values))]
    return [(name, _scalar(value))]


class ContractRegistry:
    """Discover and prepare all operations in the reviewed GetBible contracts."""

    def __init__(self, documents: Mapping[tuple[str, str], dict[str, Any]] | None = None) -> None:
        if documents is None:
            package = files("getbible_mcp").joinpath("openapi")
            documents = {
                key: json.loads(package.joinpath(f"{key[0]}-{key[1]}.json").read_text("utf-8"))
                for key in CONTRACT_URLS
            }
        self._documents = deepcopy(dict(documents))
        self._operations: dict[tuple[str, str], dict[str, _Operation]] = {}
        for key, document in self._documents.items():
            if key not in CONTRACT_URLS:
                raise ContractError(f"Unknown service/version contract: {key}")
            if not str(document.get("openapi", "")).startswith("3.1."):
                raise ContractError("Contracts must use OpenAPI 3.1 JSON Schema")
            _check_references(document)
            prefix = _server_prefix(document, CONTRACT_URLS[key])
            operations: dict[str, _Operation] = {}
            for path, raw_item in document.get("paths", {}).items():
                item = _resolve(document, raw_item)
                if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
                    raise ContractError(f"Invalid contract path: {path}")
                for method, raw_operation in item.items():
                    if method not in _HTTP_METHODS:
                        continue
                    if method != "get" and not (key[0] == "search" and method == "post"):
                        raise ContractError(f"Unsupported non-read-only operation: {method} {path}")
                    operation = _resolve(document, raw_operation)
                    operation_id = operation.get("operationId")
                    if not isinstance(operation_id, str) or not operation_id:
                        raise ContractError(f"Missing operationId: {method} {path}")
                    if operation_id in operations:
                        raise ContractError(f"Duplicate operationId: {operation_id}")
                    if "servers" in item or "servers" in operation:
                        raise ContractError("Per-operation server overrides are not supported")
                    operations[operation_id] = self._compile(
                        document, method, prefix + path, item, operation
                    )
            if not operations:
                raise ContractError(f"Contract contains no operations: {key}")
            self._operations[key] = operations

    @staticmethod
    def _compile(
        document: dict[str, Any],
        method: str,
        path: str,
        item: dict[str, Any],
        operation: dict[str, Any],
    ) -> _Operation:
        # OpenAPI operation parameters override path-item parameters by name AND location.
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for raw in [*item.get("parameters", []), *operation.get("parameters", [])]:
            parameter = _resolve(document, raw)
            location, name = parameter.get("in"), parameter.get("name")
            if location not in {"path", "query"} or not isinstance(name, str):
                raise ContractError("Only named path and query parameters are supported")
            if "schema" not in parameter or "content" in parameter:
                raise ContractError(f"Parameter {name} must use a JSON Schema")
            expected_style = "simple" if location == "path" else "form"
            if parameter.get("style", expected_style) != expected_style:
                raise ContractError(f"Unsupported parameter serialization style for {name}")
            if parameter.get("allowReserved", False):
                raise ContractError(f"Unsafe reserved query parameter serialization for {name}")
            merged[(location, name)] = parameter

        parameters: dict[str, dict[str, Any]] = {}
        properties: dict[str, Any] = {}
        required: list[str] = []
        for (location, name), parameter in merged.items():
            # A path translation and query translation can both exist in search contracts.
            # Preserve the usual unqualified path name; qualify the query collision only.
            input_name = (
                f"query.{name}" if location == "query" and ("path", name) in merged else name
            )
            if input_name in parameters:
                raise ContractError(f"Ambiguous parameter input name: {input_name}")
            parameters[input_name] = parameter
            schema = deepcopy(parameter["schema"])
            if parameter.get("description"):
                schema.setdefault("description", parameter["description"])
            if "example" in parameter:
                schema.setdefault("examples", [parameter["example"]])
            properties[input_name] = schema
            if location == "path" or parameter.get("required", False):
                required.append(input_name)

        path_names = set(_PATH_PARAMETER.findall(path))
        declared_names = {name for location, name in merged if location == "path"}
        if path_names != declared_names:
            raise ContractError(f"Path placeholders and declared parameters differ: {path}")
        parameter_schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            parameter_schema["required"] = required
        input_schema: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"parameters": parameter_schema},
            "additionalProperties": False,
            "components": deepcopy(document.get("components", {})),
        }
        input_required = ["parameters"] if required else []
        if "requestBody" in operation:
            if method != "post":
                raise ContractError("GET request bodies are not supported")
            request_body = _resolve(document, operation["requestBody"])
            content = request_body.get("content", {})
            if set(content) != {"application/json"}:
                raise ContractError("Request bodies must use application/json exclusively")
            body_schema = content["application/json"].get("schema")
            if not isinstance(body_schema, dict):
                raise ContractError("A JSON request body must define a schema")
            input_schema["properties"]["body"] = deepcopy(body_schema)
            if request_body.get("required", False):
                input_required.append("body")
        if input_required:
            input_schema["required"] = input_required
        Draft202012Validator.check_schema(input_schema)

        media_types: list[str] = []
        for status, response in operation.get("responses", {}).items():
            if not str(status).startswith("2"):
                continue
            for media_type in _resolve(document, response).get("content", {}):
                if media_type not in media_types:
                    media_types.append(media_type)
        return _Operation(
            method=method.upper(),
            path=path,
            operation=operation,
            parameters=parameters,
            input_schema=input_schema,
            accept=", ".join(media_types) or "application/json",
        )

    def _key(self, service: str, version: str) -> tuple[str, str]:
        if not isinstance(service, str) or not isinstance(version, str):
            raise ContractError("service and version must be strings")
        normalized_version = version if version.startswith("v") else f"v{version}"
        key = (service, normalized_version)
        if key not in self._documents:
            raise ContractError(f"Unknown service/version: {service}/{version}; call discover_apis")
        return key

    def _operation(self, key: tuple[str, str], operation_id: str) -> _Operation:
        if not isinstance(operation_id, str) or operation_id not in self._operations[key]:
            raise ContractError(
                f"Unknown operation for {key[0]}/{key[1]}: {operation_id}; call discover_apis"
            )
        return self._operations[key][operation_id]

    def catalog(self) -> list[dict[str, Any]]:
        """List every service/version and operation without large response schemas."""
        return [
            {
                "service": key[0],
                "version": key[1],
                "title": document.get("info", {}).get("title", "GetBible"),
                "description": document.get("info", {}).get("description", ""),
                "openapi_url": CONTRACT_URLS[key],
                "resource_uri": f"getbible://openapi/{key[0]}/{key[1]}",
                "contract_sha256": hashlib.sha256(
                    json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "operations": [
                    {
                        "operation_id": operation_id,
                        "method": operation.method,
                        "path": operation.path,
                        "summary": operation.operation.get("summary", ""),
                    }
                    for operation_id, operation in self._operations[key].items()
                ],
            }
            for key, document in self._documents.items()
        ]

    def document(self, service: str, version: str) -> dict[str, Any]:
        """Return the full upstream document, including all response schemas."""
        return deepcopy(self._documents[self._key(service, version)])

    def describe(self, service: str, version: str, operation_id: str) -> dict[str, Any]:
        """Return an operation and a self-contained schema for parameters/body."""
        key = self._key(service, version)
        operation = self._operation(key, operation_id)
        return deepcopy(
            {
                "service": key[0],
                "version": key[1],
                "operation_id": operation_id,
                "method": operation.method,
                "path": operation.path,
                "openapi_url": CONTRACT_URLS[key],
                "input_schema": operation.input_schema,
                "parameters": [
                    {"input_name": name, **parameter}
                    for name, parameter in operation.parameters.items()
                ],
                "operation": operation.operation,
                "components": self._documents[key].get("components", {}),
                "parameter_usage": (
                    "Pass parameters as an object keyed by input_name. Values retain their JSON "
                    "types; arrays become repeated query parameters when the contract specifies "
                    "explode=true. On a path/query name collision, the unqualified name is the "
                    "path parameter and query.<name> is the query parameter. Omit unused fields; "
                    "defaults are applied upstream. Pass a JSON request body separately as body."
                ),
            }
        )

    def prepare(
        self,
        service: str,
        version: str,
        operation_id: str,
        parameters: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> PreparedRequest:
        """Validate the complete input and encode only an advertised operation."""
        key = self._key(service, version)
        operation = self._operation(key, operation_id)
        supplied: dict[str, Any] = {"parameters": parameters if parameters is not None else {}}
        if body is not None:
            supplied["body"] = body
        error = next(Draft202012Validator(operation.input_schema).iter_errors(supplied), None)
        if error is not None:
            location = ".".join(str(part) for part in error.absolute_path) or "input"
            raise ContractError(f"Invalid {location}: {error.message}")
        if not isinstance(supplied["parameters"], dict):
            raise ContractError("parameters must be an object")
        if body is not None and not isinstance(body, dict):
            raise ContractError("body must be a JSON object")
        path_values: dict[str, str] = {}
        query: list[tuple[str, str]] = []
        for input_name, value in supplied["parameters"].items():
            parameter = operation.parameters[input_name]
            if parameter["in"] == "path":
                path_values[parameter["name"]] = _path_value(value, input_name)
            else:
                query.extend(_query_values(parameter, value))
        path = _PATH_PARAMETER.sub(lambda match: path_values[match.group(1)], operation.path)
        return PreparedRequest(
            service=key[0],
            version=key[1],
            operation_id=operation_id,
            method=operation.method,
            path=path,
            params=query,
            body=deepcopy(body),
            accept=operation.accept,
            operation=deepcopy(operation.operation),
        )
