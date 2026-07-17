from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from openapi_spec_validator import validate

from getbible_mcp.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


def test_all_static_json_is_valid() -> None:
    for path in (ROOT / "site").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))

    server_metadata = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server_metadata["name"] == "net.getbible/mcp"
    assert server_metadata["remotes"][0] == {
        "type": "streamable-http",
        "url": "https://mcp.getbible.net/v2",
    }
    assert server_metadata["packages"][0] == {
        "registryType": "pypi",
        "identifier": "getbible-mcp",
        "version": "1.0.0",
        "transport": {"type": "stdio"},
    }


def test_native_api_openapi_document_is_valid() -> None:
    document = json.loads((ROOT / "site/v2/openapi.json").read_text(encoding="utf-8"))
    validate(document)


def test_static_site_only_advertises_api_v2() -> None:
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "site").rglob("*")
        if path.is_file()
    ).lower()
    assert "api v3" not in content
    assert "/v3" not in content


def test_nginx_routes_only_exact_v2_to_application() -> None:
    config = (
        ROOT / "deploy/nginx/sites-available/mcp.getbible.net.conf"
    ).read_text(encoding="utf-8")
    assert "location = /v2" in config
    assert "root /opt/getbible-mcp/current/site" in config
    assert "proxy_buffering off" in config
    assert "limit_req" not in config


def test_pypi_workflow_uses_trusted_publishing_after_validation() -> None:
    workflow = (ROOT / ".github/workflows/publish-pypi.yml").read_text(encoding="utf-8")
    assert "needs: validate" in workflow
    assert "needs: package" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "PYPI_TOKEN" not in workflow


def test_cli_defaults_to_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GETBIBLE_MCP_TRANSPORT", raising=False)
    assert build_parser().parse_args([]).transport == "stdio"


@pytest.mark.parametrize("script", ["manage", "scripts/check"])
def test_bash_scripts_parse(script: str) -> None:
    result = subprocess.run(
        ["bash", "-n", str(ROOT / script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
