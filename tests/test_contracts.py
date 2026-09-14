"""Contract coverage, input boundaries and safe request serialization."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator

from getbible_mcp.contracts import CONTRACT_URLS, ContractError, ContractRegistry


@pytest.fixture(scope="module")
def registry() -> ContractRegistry:
    return ContractRegistry()


def _example(parameter: dict[str, Any]) -> Any:
    if "example" in parameter:
        return parameter["example"]
    schema = parameter["schema"]
    if "enum" in schema:
        return schema["enum"][0]
    if schema.get("type") == "integer":
        return schema.get("minimum", 1)
    return {
        "translation": "kjv",
        "abbreviation": "kjv",
        "reference": "John3:16",
        "search": "faith",
        "segment": "faith",
        "entry": "G26",
    }.get(parameter["name"], "example")


def test_every_published_operation_can_be_discovered_described_and_prepared(
    registry: ContractRegistry,
) -> None:
    """A new path or method in any snapshot cannot silently lose MCP coverage."""
    catalogs = registry.catalog()
    assert {(item["service"], item["version"]) for item in catalogs} == set(CONTRACT_URLS)
    for catalog in catalogs:
        service, version = catalog["service"], catalog["version"]
        document = registry.document(service, version)
        published = {
            operation["operationId"]: (method.upper(), path)
            for path, path_item in document["paths"].items()
            for method, operation in path_item.items()
            if method in {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
        }
        assert {item["operation_id"] for item in catalog["operations"]} == set(published)
        for operation_id, (method, _) in published.items():
            described = registry.describe(service, version, operation_id)
            parameters = {
                parameter["input_name"]: _example(parameter)
                for parameter in described["parameters"]
                if parameter["in"] == "path" or parameter.get("required", False)
            }
            Draft202012Validator(described["input_schema"]).validate({"parameters": parameters})
            prepared = registry.prepare(service, version, operation_id, parameters)
            assert prepared.method == method
            assert "{" not in prepared.path and "}" not in prepared.path
            assert prepared.path.startswith("/") and not prepared.path.startswith("//")
            assert "?" not in prepared.path and "#" not in prepared.path
            assert prepared.operation["responses"] == described["operation"]["responses"]
            assert described["components"] == document.get("components", {})


@pytest.mark.parametrize(
    ("service", "version", "operation_id", "parameters", "expected"),
    [
        (
            "api",
            "v2",
            "getChapter",
            {"abbreviation": "kjv", "book": 43, "chapter": 3},
            "/v2/kjv/43/3.json",
        ),
        (
            "api",
            "v3",
            "getChapter",
            {"translation": "kjv", "book": 43, "chapter": 3},
            "/v3/kjv/43/3.json",
        ),
        ("bookmarks", "v1", "getTopic", {"id": "adultery"}, "/v1/topics/adultery.json"),
        (
            "dictionaries",
            "v1",
            "getDictionaryEntry",
            {"dictionary": "strongsgreek", "entry": "G26"},
            "/v1/strongsgreek/G26.json",
        ),
        (
            "commentaries",
            "v1",
            "getCommentaryChapter",
            {"commentary": "barnes", "book": 1, "chapter": 0},
            "/v1/barnes/1/0.json",
        ),
        ("query", "v3", "health", {}, "/healthz"),
        ("search", "v2", "searchDefault", {"q": "faith"}, "/v2"),
    ],
)
def test_relative_and_absolute_contract_paths_resolve_once(
    registry: ContractRegistry,
    service: str,
    version: str,
    operation_id: str,
    parameters: dict[str, Any],
    expected: str,
) -> None:
    assert registry.prepare(service, version, operation_id, parameters).path == expected


def test_repeated_query_values_typed_scalars_and_name_collisions(
    registry: ContractRegistry,
) -> None:
    request = registry.prepare(
        "search",
        "v3",
        "search",
        {
            "translation": "kjv",
            "query.translation": "web",
            "search": "faith & hope",
            "book": ["Genesis", 2],
            "books": "John,Romans",
            "exclude": ["fear", "evil"],
            "case_sensitive": False,
            "limit": 25,
            "offset": 0,
        },
    )
    url = httpx.URL("https://search.getbible.net" + request.path, params=request.params)
    assert url.path == "/v3/kjv/faith & hope"
    assert "faith%20%26%20hope" in str(url)
    assert url.params.get_list("book") == ["Genesis", "2"]
    assert url.params.get_list("exclude") == ["fear", "evil"]
    assert url.params["translation"] == "web"
    assert url.params["case_sensitive"] == "false"
    assert url.params["limit"] == "25"
    assert url.params["offset"] == "0"
    assert url.params["books"] == "John,Romans"


def test_post_body_preserves_null_unions_and_upstream_precedence(
    registry: ContractRegistry,
) -> None:
    body = {
        "q": "hope",
        "book": ["John", 45],
        "books": [1, "Genesis"],
        "exclude": "fear",
        "limit": None,
    }
    request = registry.prepare(
        "search", "v2", "searchDefaultPost", {"q": "faith", "limit": 10}, body
    )
    assert request.method == "POST"
    assert request.params == [("q", "faith"), ("limit", "10")]
    assert request.body == body
    body["q"] = "changed after preparation"
    assert request.body is not None and request.body["q"] == "hope"
    assert registry.prepare("search", "v2", "searchDefaultPost", {"q": "faith"}).body is None
    assert registry.prepare("search", "v2", "searchDefault", {"q": "faith"}).params == [
        ("q", "faith")
    ]


@pytest.mark.parametrize(
    ("operation_id", "parameters", "body"),
    [
        ("searchDefault", {"limit": 0}, None),
        ("searchDefault", {"limit": 101}, None),
        ("searchDefault", {"limit": "10"}, None),
        ("searchDefault", {"limit": True}, None),
        ("searchDefault", {"offset": -1}, None),
        ("searchDefault", {"offset": 10001}, None),
        ("searchDefault", {"proximity": 101}, None),
        ("searchDefault", {"q": ""}, None),
        ("searchDefault", {"q": "a" * 501}, None),
        ("searchDefault", {"words": "xor"}, None),
        ("searchDefault", {"book": [1] * 84}, None),
        ("searchDefault", {"book": [True]}, None),
        ("searchDefault", {"exclude": ["a"] * 33}, None),
        ("searchDefault", {"exclude": [""]}, None),
        ("searchDefault", {"exclude": ["a" * 101]}, None),
        ("searchDefault", {"unknown": "value"}, None),
        ("searchDefault", {}, {"q": "faith"}),
        ("searchDefaultPost", {}, {"limit": 101}),
        ("searchDefaultPost", {}, {"unknown": "value"}),
        ("searchDefaultPost", {}, {"book": [None]}),
        ("search", {"search": "faith"}, None),
    ],
)
def test_invalid_inputs_are_rejected_before_any_request(
    registry: ContractRegistry,
    operation_id: str,
    parameters: dict[str, Any],
    body: dict[str, Any] | None,
) -> None:
    with pytest.raises(ContractError, match="Invalid"):
        registry.prepare("search", "v3", operation_id, parameters, body)


@pytest.mark.parametrize(
    "reference", ["", ".", "..", "../John", "John/3", "John\\3", "John\x00", "John\r\n"]
)
def test_unsafe_path_segments_are_rejected(registry: ContractRegistry, reference: str) -> None:
    with pytest.raises(ContractError, match="safe path segment"):
        registry.prepare(
            "query", "v3", "getScripture", {"translation": "kjv", "reference": reference}
        )


def test_reserved_characters_and_unicode_are_encoded_once(registry: ContractRegistry) -> None:
    reference = "John3:16;Psalm 23?x=1#\u03b1%2F"  # Greek alpha exercises UTF-8 encoding.
    request = registry.prepare(
        "query", "v3", "getScripture", {"translation": "kjv", "reference": reference}
    )
    url = httpx.URL("https://query.getbible.net" + request.path)
    assert url.path == f"/v3/kjv/{reference}"
    assert not url.query and not url.fragment
    assert "%252F" in request.path
    assert "%3F" in request.path and "%23" in request.path and "%CE%B1" in request.path


def test_service_specific_numeric_and_identifier_constraints(registry: ContractRegistry) -> None:
    registry.prepare(
        "commentaries",
        "v1",
        "getCommentaryChapter",
        {"commentary": "barnes", "book": 83, "chapter": 0},
    )
    registry.prepare("api", "v2", "getBook", {"abbreviation": "kjv", "book": 89})
    for service, operation, parameters in [
        ("bookmarks", "getBook", {"book": 67}),
        ("bookmarks", "getTopic", {"id": "Display Name"}),
        ("bookmarks", "getLocale", {"locale": "EN"}),
        ("commentaries", "getCommentaryBook", {"commentary": "barnes", "book": 84}),
        ("dictionaries", "getSchema", {"document": "unpublished-schema"}),
    ]:
        with pytest.raises(ContractError):
            registry.prepare(service, "v1", operation, parameters)


@pytest.mark.parametrize(
    ("service", "version", "operation_id"),
    [("https://example.com", "v1", "getBook"), ("api", "v1", "getBook"), ("api", "v2", "DELETE")],
)
def test_only_known_service_version_and_operation_are_allowed(
    registry: ContractRegistry, service: str, version: str, operation_id: str
) -> None:
    with pytest.raises(ContractError, match="Unknown"):
        registry.prepare(service, version, operation_id)


def test_discovery_does_not_mutate_registry_and_version_shorthand_is_supported(
    registry: ContractRegistry,
) -> None:
    described = registry.describe("search", "3", "searchDefault")
    described["input_schema"]["properties"]["parameters"]["properties"]["limit"]["maximum"] = 1000
    document = registry.document("search", "v3")
    document["paths"].clear()
    assert registry.describe("search", "v3", "searchDefault")["version"] == "v3"
    with pytest.raises(ContractError):
        registry.prepare("search", "3", "searchDefault", {"limit": 101})
    assert registry.document("search", "v3")["paths"]


def test_operation_parameters_override_shared_parameters_by_location(
    registry: ContractRegistry,
) -> None:
    document = registry.document("search", "v3")
    override = deepcopy(document["components"]["parameters"]["limit"])
    override["schema"]["maximum"] = 5
    document["paths"]["/v3"]["get"]["parameters"] = [override]
    modified = ContractRegistry({("search", "v3"): document})
    with pytest.raises(ContractError):
        modified.prepare("search", "v3", "searchDefault", {"limit": 6})
    assert modified.prepare("search", "v3", "searchDefaultPost", {"limit": 6}).params == [
        ("limit", "6")
    ]


@pytest.mark.parametrize("change", ["method", "external_ref", "style", "server", "missing_id"])
def test_unsupported_contract_changes_fail_explicitly(
    registry: ContractRegistry, change: str
) -> None:
    document = registry.document("search", "v3")
    if change == "method":
        document["paths"]["/v3"]["delete"] = {"operationId": "deleteSearch", "responses": {}}
    elif change == "external_ref":
        document["components"]["parameters"]["q"]["schema"] = {"$ref": "https://example.com/schema"}
    elif change == "style":
        document["components"]["parameters"]["q"]["style"] = "deepObject"
    elif change == "server":
        document["servers"] = [{"url": "https://example.com"}]
    else:
        del document["paths"]["/v3"]["get"]["operationId"]
    with pytest.raises(ContractError):
        ContractRegistry({("search", "v3"): document})


def _synthetic_contract(
    schema: dict[str, Any], *, location: str = "query", explode: bool = True
) -> dict[str, Any]:
    """Represent a new operation without depending on today's endpoint inventory."""
    path = "/v3/example/{value}" if location == "path" else "/v3/example"
    return {
        "openapi": "3.1.0",
        "info": {"title": "Fixture", "version": "1"},
        "paths": {
            path: {
                "get": {
                    "operationId": "newOperation",
                    "parameters": [
                        {
                            "name": "value",
                            "in": location,
                            "required": location == "path",
                            "explode": explode,
                            "schema": schema,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


@pytest.mark.parametrize("explode", [True, False])
def test_new_flat_object_query_parameters_serialize_as_standard_form(explode: bool) -> None:
    schema = {
        "type": "object",
        "properties": {"role": {"type": "string"}, "active": {"type": "boolean"}},
        "additionalProperties": False,
    }
    registry = ContractRegistry({("search", "v3"): _synthetic_contract(schema, explode=explode)})
    prepared = registry.prepare(
        "search", "v3", "newOperation", {"value": {"role": "reader", "active": False}}
    )
    assert prepared.params == (
        [("role", "reader"), ("active", "false")]
        if explode
        else [("value", "role,reader,active,false")]
    )


@pytest.mark.parametrize("explode", [True, False])
def test_new_flat_object_path_parameters_use_simple_serialization(explode: bool) -> None:
    schema = {"type": "object", "additionalProperties": {"type": ["string", "integer"]}}
    registry = ContractRegistry(
        {("search", "v3"): _synthetic_contract(schema, location="path", explode=explode)}
    )
    prepared = registry.prepare(
        "search", "v3", "newOperation", {"value": {"label": "faith & hope", "page": 2}}
    )
    assert prepared.path == (
        "/v3/example/label=faith%20%26%20hope,page=2"
        if explode
        else "/v3/example/label,faith%20%26%20hope,page,2"
    )


@pytest.mark.parametrize("location", ["path", "query"])
def test_refs_unions_and_split_allof_constraints_keep_scalar_arrays_supported(
    location: str,
) -> None:
    document = _synthetic_contract(
        {"$ref": "#/components/schemas/Values"}, location=location, explode=False
    )
    document["components"] = {
        "schemas": {
            "Values": {
                "allOf": [
                    {"type": "array"},
                    {"items": {"anyOf": [{"type": "integer"}, {"type": "string"}]}},
                ]
            }
        }
    }
    registry = ContractRegistry({("search", "v3"): document})
    prepared = registry.prepare("search", "v3", "newOperation", {"value": [1, "John"]})
    if location == "path":
        assert prepared.path == "/v3/example/1,John"
    else:
        assert prepared.params == [("value", "1,John")]


@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"type": ["string", "null"]},
        {"type": "array"},
        {"$id": "https://example.test/scoped", "type": "string"},
        {"$dynamicRef": "#/components/schemas/Value", "type": "string"},
        {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
        {"type": "object", "properties": {"label": {"type": "string"}}},
        {"type": "object", "additionalProperties": {"type": "object"}},
        {
            "type": "object",
            "properties": {"nested": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
        {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "object"}}]},
    ],
)
@pytest.mark.parametrize("location", ["path", "query"])
def test_unsupported_optional_and_required_wire_shapes_fail_at_registry_construction(
    schema: dict[str, Any], location: str
) -> None:
    # Query inputs are optional: discovery must reject unsupported declarations
    # before any caller happens to provide their value.
    with pytest.raises(ContractError, match="wire shape"):
        ContractRegistry({("search", "v3"): _synthetic_contract(schema, location=location)})


def test_reference_sibling_constraints_are_conjoined_for_wire_shape_proof() -> None:
    document = _synthetic_contract({"$ref": "#/components/schemas/Map", "type": "object"})
    document["components"] = {
        "schemas": {
            "Map": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            }
        }
    }
    registry = ContractRegistry({("search", "v3"): document})
    assert registry.prepare("search", "v3", "newOperation", {"value": {"word": "hope"}}).params == [
        ("word", "hope")
    ]
    document["components"]["schemas"]["Map"]["additionalProperties"] = {"type": "array"}
    with pytest.raises(ContractError, match="wire shape"):
        ContractRegistry({("search", "v3"): document})


def test_flat_query_object_keys_and_values_cannot_inject_query_parameters() -> None:
    schema = {"type": "object", "additionalProperties": {"type": "string"}}
    registry = ContractRegistry({("search", "v3"): _synthetic_contract(schema)})
    prepared = registry.prepare(
        "search", "v3", "newOperation", {"value": {"word&limit": "faith?limit=99#fragment"}}
    )
    url = httpx.URL("https://search.getbible.net" + prepared.path, params=prepared.params)
    assert list(url.params.multi_items()) == [("word&limit", "faith?limit=99#fragment")]
    assert not url.fragment


@pytest.mark.parametrize("schema", [{}, {"type": "array"}, {"type": ["object", "null"]}])
def test_non_object_request_body_roots_fail_before_publication(schema: dict[str, Any]) -> None:
    document = _synthetic_contract({"type": "string"})
    item = document["paths"]["/v3/example"]
    item["post"] = item.pop("get")
    item["post"]["requestBody"] = {"content": {"application/json": {"schema": schema}}}
    with pytest.raises(ContractError, match="JSON request body"):
        ContractRegistry({("search", "v3"): document})


def test_object_request_bodies_keep_arbitrary_nested_json_supported() -> None:
    document = _synthetic_contract({"type": "string"})
    item = document["paths"]["/v3/example"]
    item["post"] = item.pop("get")
    item["post"]["requestBody"] = {
        "content": {
            "application/json": {
                "schema": {
                    "allOf": [{"type": "object"}, {"properties": {"nested": {"type": "array"}}}],
                }
            }
        }
    }
    registry = ContractRegistry({("search", "v3"): document})
    body = {"nested": [[None, {"key": True}]]}
    assert registry.prepare("search", "v3", "newOperation", body=body).body == body


@pytest.mark.parametrize("location", ["document", "operation"])
def test_effective_authentication_requirements_fail_during_discovery(location: str) -> None:
    document = _synthetic_contract({"type": "string"})
    operation = document["paths"]["/v3/example"]["get"]
    target = document if location == "document" else operation
    target["security"] = [{"bearer": []}]
    with pytest.raises(ContractError, match="Authenticated upstream"):
        ContractRegistry({("search", "v3"): document})


def test_public_security_override_and_empty_requirement_are_supported() -> None:
    document = _synthetic_contract({"type": "string"})
    document["security"] = [{"bearer": []}]
    operation = document["paths"]["/v3/example"]["get"]
    for public_security in ([], [{}]):
        operation["security"] = public_security
        registry = ContractRegistry({("search", "v3"): document})
        assert registry.prepare("search", "v3", "newOperation").method == "GET"


@pytest.mark.parametrize("location", ["path", "operation"])
def test_per_operation_server_overrides_are_rejected(location: str) -> None:
    document = _synthetic_contract({"type": "string"})
    item = document["paths"]["/v3/example"]
    target = item if location == "path" else item["get"]
    target["servers"] = [{"url": "https://search.getbible.net/alternate"}]
    with pytest.raises(ContractError, match="server overrides"):
        ContractRegistry({("search", "v3"): document})
