from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from urllib.error import HTTPError

import httpx
import pytest

from getbible_mcp.contracts import CONTRACT_URLS

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("tag_commit", "published", "release_exists", "needed", "upload"),
    [
        (None, False, False, "true", "true"),
        ("a" * 40, True, True, "false", "false"),
        ("a" * 40, False, False, "true", "true"),
        ("a" * 40, True, False, "true", "false"),
        (None, True, False, "true", "false"),
        ("a" * 40, False, True, "true", "true"),
    ],
)
def test_release_plan_is_idempotent_and_recovers_partial_publication(
    monkeypatch: pytest.MonkeyPatch,
    tag_commit: str | None,
    published: bool,
    release_exists: bool,
    needed: str,
    upload: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    release = importlib.import_module("release_state")
    result = release.release_plan("2.4.7", "b" * 40, tag_commit, published, release_exists)
    assert result["needed"] == needed
    assert result["publish"] == upload
    assert result["ref"] == (tag_commit or "b" * 40)
    assert result["tag"] == "v2.4.7"


def test_release_network_failure_is_not_treated_as_unpublished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    release = importlib.import_module("release_state")

    def unavailable(*args: object, **kwargs: object) -> None:
        raise HTTPError("https://pypi.org/", 503, "Unavailable", {}, None)

    monkeypatch.setattr(release, "urlopen", unavailable)
    with pytest.raises(HTTPError):
        release.optional_json("https://pypi.org/")


@pytest.mark.parametrize(
    ("kinds", "complete"),
    [([], False), (["bdist_wheel"], False), (["sdist"], False), (["sdist", "bdist_wheel"], True)],
)
def test_partial_package_upload_is_retried(
    monkeypatch: pytest.MonkeyPatch, kinds: list[str], complete: bool,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    release = importlib.import_module("release_state")
    package = {"info": {"version": "2.4.7"}, "urls": [{"packagetype": kind} for kind in kinds]}
    assert release.package_complete(package, "2.4.7") is complete


@pytest.mark.parametrize(
    "invalid", [
        "unknown-operation", "write-operation", "invalid-schema", "nested-query", "security",
        "nonfinite-constant", "nonfinite-number",
    ],
)
def test_contract_refresh_rejects_unsupported_changes_before_any_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    refresh = importlib.import_module("refresh_contracts")
    documents = {
        key: json.loads((ROOT / "src/getbible_mcp/openapi" / f"{key[0]}-{key[1]}.json").read_text())
        for key in CONTRACT_URLS
    }
    # A valid first change must remain unwritten when another document is unsupported.
    documents[("api", "v2")]["info"]["description"] = "Updated upstream documentation"
    target = documents[("bookmarks", "v1")]
    path_item = target["paths"]["/index.json"]
    if invalid == "unknown-operation":
        path_item["connect"] = {"operationId": "connect", "responses": {"200": {"description": "ok"}}}
    elif invalid == "write-operation":
        path_item["delete"] = {"operationId": "deleteIndex", "responses": {"200": {"description": "ok"}}}
    elif invalid == "invalid-schema":
        target["paths"] = []
    elif invalid == "nested-query":
        path_item["get"]["parameters"] = [{
            "in": "query", "name": "newOptional", "required": False,
            "schema": {"type": "array", "items": {"type": "object"}},
        }]
    elif invalid == "security":
        target.setdefault("components", {}).setdefault("securitySchemes", {})["bearer"] = {
            "type": "http", "scheme": "bearer",
        }
        path_item["get"]["security"] = [{"bearer": []}]
    else:
        target["x-probe"] = "NONFINITE"
    contents = {CONTRACT_URLS[key]: json.dumps(document).encode() for key, document in documents.items()}
    if invalid.startswith("nonfinite"):
        url = CONTRACT_URLS[("bookmarks", "v1")]
        contents[url] = contents[url].replace(
            b'"NONFINITE"', b"NaN" if invalid == "nonfinite-constant" else b"1e400",
        )
    for key in CONTRACT_URLS:
        name = f"{key[0]}-{key[1]}.json"
        for directory in ("src/getbible_mcp/openapi", "site/contracts"):
            path = tmp_path / directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / directory / name).read_bytes())
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    original_client = httpx.Client
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=contents[str(request.url)])
    )
    monkeypatch.setattr(refresh.httpx, "Client", lambda **kwargs: original_client(transport=transport))
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["refresh_contracts.py", "--write"])
    assert refresh.main() == 2
    assert all(path.read_bytes() == content for path, content in before.items())


def test_sync_workflow_keeps_review_and_validates_before_remote_mutation() -> None:
    workflow = (ROOT / ".github/workflows/sync-openapi.yml").read_text()
    assert "schedule:" in workflow and "workflow_dispatch:" in workflow
    assert workflow.index("bash scripts/check") < workflow.index("git push")
    assert "--force-with-lease=" in workflow
    assert 'gh workflow run test.yml --ref "$BOT_BRANCH"' in workflow
    assert "gh pr merge" not in workflow
    assert "--auto" not in workflow
    assert "git push origin main" not in workflow


def test_existing_release_artifact_bytes_must_match_before_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    verifier = importlib.import_module("verify_pypi_artifacts")
    wheel = tmp_path / "getbible_mcp-2.4.7-py3-none-any.whl"
    wheel.write_bytes(b"validated wheel")
    (tmp_path / "getbible_mcp-2.4.7.tar.gz").write_bytes(b"validated source")
    package = {"info": {"version": "2.4.7"}, "urls": [{
        "filename": wheel.name, "digests": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
    }]}
    verifier.verify_artifacts(tmp_path, "2.4.7", package)
    with pytest.raises(ValueError, match="both validated distributions"):
        verifier.verify_artifacts(tmp_path, "2.4.7", package, require_complete=True)
    wheel.write_bytes(b"different rebuilt wheel")
    with pytest.raises(ValueError, match="differs from the validated artifact"):
        verifier.verify_artifacts(tmp_path, "2.4.7", package)
