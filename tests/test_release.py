from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from getbible_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]
VERIFY_RELEASE = ROOT / "scripts/verify_release.py"


def test_release_versions_match_package_tag() -> None:
    result = subprocess.run(
        [sys.executable, str(VERIFY_RELEASE), f"v{__version__}"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_release_version_mismatch_fails_closed() -> None:
    result = subprocess.run(
        [sys.executable, str(VERIFY_RELEASE), "v9.9.9"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "version declarations differ" in result.stderr


def copy_version_files(destination: Path) -> None:
    import shutil

    for relative in (
        "pyproject.toml", "src/getbible_mcp/__init__.py", "server.json",
        "site/manifest.json", "site/v2/manifest.json",
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_patch_bump_updates_every_declaration_and_keeps_api_versions(tmp_path: Path) -> None:
    import json
    import tomllib

    copy_version_files(tmp_path)
    source = tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]["version"]
    major, minor, patch = source.split(".")
    expected = f"{major}.{minor}.{int(patch) + 1}"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump_version.py"), "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
    readback = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump_version.py"), "--current", "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert readback.returncode == 0, readback.stderr
    assert readback.stdout.strip() == expected
    metadata = json.loads((tmp_path / "server.json").read_text())
    assert metadata["version"] == expected
    assert all(package["version"] == expected for package in metadata["packages"])
    manifest = json.loads((tmp_path / "site/v2/manifest.json").read_text())
    assert manifest["mcp_server_version"] == expected
    assert {(api["service"], api["api_version"]) for api in manifest["apis"]} == {
        (api["service"], api["api_version"])
        for api in json.loads((ROOT / "site/v2/manifest.json").read_text())["apis"]
    }


def test_patch_bump_rejects_mismatched_nested_version_without_writing(tmp_path: Path) -> None:
    import json

    copy_version_files(tmp_path)
    registry = tmp_path / "server.json"
    document = json.loads(registry.read_text())
    document["packages"][0]["version"] = "2.99.99"
    registry.write_text(json.dumps(document))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump_version.py"), "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "declarations differ" in result.stderr
    assert all(path.read_bytes() == content for path, content in before.items())


def test_patch_bump_rejects_nonstable_versions_without_writing(tmp_path: Path) -> None:
    copy_version_files(tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.write_text(path.read_text().replace(__version__, "2.1.0rc1"))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump_version.py"), "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "stable 2.MINOR.PATCH" in result.stderr
    assert all(path.read_bytes() == content for path, content in before.items())
