"""Keep portable and compatibility connections, branding and review materials consistent."""

from __future__ import annotations

import base64
import json
import tomllib
from importlib.resources import files
from pathlib import Path

from tests.test_server_http import TOOL_NAMES, http_session

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin/getbible"


def test_plugin_metadata_and_assets_are_self_contained() -> None:
    portable = json.loads((PLUGIN / "plugin.json").read_text())
    compatibility = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert portable["name"] == PLUGIN.name == compatibility["name"]
    assert portable["version"] == compatibility["version"]
    interface = portable["extensions"]["com.openai"]["interface"]
    assert interface == compatibility["interface"]
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["urls"]
    assert interface["websiteURL"] == portable["homepage"] == metadata["Homepage"]
    assert portable["author"]["url"] == metadata["Homepage"]
    assert interface["capabilities"] == ["Read"]
    assert compatibility["mcpServers"] == "./.mcp.json"
    assert "apps" not in portable["extensions"]["com.openai"]
    for field in ("logo", "composerIcon"):
        asset = PLUGIN / interface[field]
        assert asset.resolve().is_relative_to(PLUGIN.resolve())
        assert asset.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (PLUGIN / interface["logo"]).read_bytes() == files("getbible_mcp").joinpath(
        "assets", "icon.png"
    ).read_bytes()
    for field, document in (("privacyPolicyURL", "PRIVACY.md"), ("termsOfServiceURL", "TERMS.md")):
        assert interface[field] == f"https://github.com/getbible/mcp/blob/main/docs/{document}"
        assert (ROOT / "docs" / document).is_file()


def test_connection_and_review_materials_use_the_official_anonymous_endpoint() -> None:
    portable = json.loads((PLUGIN / "mcp.json").read_text())
    compatibility = json.loads((PLUGIN / ".mcp.json").read_text())
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert portable["mcpServers"] == {
        "getbible": {"type": "streamable-http", "url": "https://mcp.getbible.net/"}
    }
    assert compatibility == {
        "mcpServers": {"getbible": {"type": "http", "url": "https://mcp.getbible.net/"}}
    }
    submission = json.loads((PLUGIN / "submission.json").read_text())
    assert submission["connection"]["server_url"] == "https://mcp.getbible.net/"
    assert submission["connection"]["authentication"] == "none"
    assert submission["connection"]["custom_ui"] is False
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["urls"]
    assert submission["listing"]["website_url"] == metadata["Homepage"]
    assert submission["listing"]["documentation_url"] == metadata["Documentation"]
    assert (PLUGIN / submission["listing"]["logo_path"]).is_file()
    assert (PLUGIN / submission["test_cases_path"]).is_file()


async def test_discovered_branding_and_static_tool_catalog_match_the_runtime() -> None:
    async with http_session() as (client, http):
        assert client.server_info is not None and client.server_info.icons
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["urls"]
        assert client.server_info.website_url == metadata["Homepage"]
        discovery = (await http.get("/")).json()
        assert discovery["documentation"] == metadata["Documentation"]
        assert discovery["streamable_http"] != discovery["documentation"]
        icon = client.server_info.icons[0]
        assert icon.mime_type == "image/png"
        assert icon.sizes == ["230x230"]
        assert base64.b64decode(icon.src.split(",", 1)[1], validate=True) == (
            PLUGIN / "assets/logo.png"
        ).read_bytes()
        catalog = json.loads((ROOT / "site/v2/tool-catalog.json").read_text())
        assert {item["name"] for item in catalog["tools"]} == TOOL_NAMES
