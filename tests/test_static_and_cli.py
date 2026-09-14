from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from openapi_spec_validator import validate

from getbible_mcp import __version__
from getbible_mcp.cli import build_parser
from getbible_mcp.contracts import CONTRACT_URLS

ROOT = Path(__file__).resolve().parents[1]


def test_all_static_json_is_valid() -> None:
    for path in (ROOT / "site").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))

    server_metadata = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server_metadata["name"] == "net.getbible/mcp"
    assert server_metadata["packages"][0] == {
        "registryType": "pypi",
        "identifier": "getbible-mcp",
        "version": __version__,
        "transport": {"type": "stdio"},
    }


def test_static_site_publishes_every_reviewed_contract() -> None:
    for service, version in CONTRACT_URLS:
        published = ROOT / "site/contracts" / f"{service}-{version}.json"
        packaged = ROOT / "src/getbible_mcp/openapi" / published.name
        assert published.read_bytes() == packaged.read_bytes()
        validate(json.loads(published.read_text(encoding="utf-8")))


def test_test_workflow_builds_downloadable_packages_after_all_validation() -> None:
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert 'python: ["3.11", "3.12", "3.13", "3.14"]' in workflow
    assert "needs: [python]" in workflow
    assert "Smoke-test the built wheel" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "name: python-package-distributions" in workflow
    assert "retention-days: 30" in workflow


def test_testpypi_workflow_is_manual_and_tokenless() -> None:
    workflow = (ROOT / ".github/workflows/publish-testpypi.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in workflow
    assert "uses: ./.github/workflows/test.yml" in workflow
    assert "needs: validate" in workflow
    assert "name: testpypi" in workflow
    assert "id-token: write" in workflow
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "PYPI_TOKEN" not in workflow


def test_pypi_workflow_uses_validated_artifact_and_protected_token() -> None:
    workflow = (ROOT / ".github/workflows/publish-pypi.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert 'default: ""' in workflow
    assert "branches: [main]" in workflow
    assert "needs: [prepare, validate, release-check]" in workflow
    assert "ref: ${{ needs.prepare.outputs.ref }}" in workflow
    assert "if: needs.prepare.outputs.publish == 'true'" in workflow
    assert "types: [published]" not in workflow
    assert "actions/download-artifact@v8" in workflow
    assert "name: python-package-distributions" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "password: ${{ secrets.PYPI_MCP_TOKEN }}" in workflow
    assert "print-hash: true" in workflow


def test_cli_defaults_to_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GETBIBLE_MCP_TRANSPORT", raising=False)
    assert build_parser().parse_args([]).transport == "stdio"


@pytest.mark.parametrize("script", ["scripts/check"])
def test_bash_scripts_parse(script: str) -> None:
    result = subprocess.run(
        ["bash", "-n", str(ROOT / script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
