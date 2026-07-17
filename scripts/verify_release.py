#!/usr/bin/env python3
"""Verify that one release tag matches every published project version."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalized_tag(tag: str) -> str:
    """Return a version from a GitHub tag such as v1.2.3 or 1.2.3."""

    value = tag.removeprefix("refs/tags/")
    return value[1:] if value.startswith("v") else value


def declared_versions() -> dict[str, str]:
    """Read all public version declarations without importing the package."""

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "site/v2/manifest.json").read_text(encoding="utf-8"))
    init_text = (ROOT / "src/getbible_mcp/__init__.py").read_text(encoding="utf-8")
    package_match = re.search(r'^__version__\s*=\s*"([^"]+)"$', init_text, re.MULTILINE)
    if package_match is None:
        raise ValueError("src/getbible_mcp/__init__.py has no __version__ declaration")

    return {
        "pyproject.toml": str(pyproject["project"]["version"]),
        "server.json": str(server["version"]),
        "site/v2/manifest.json": str(manifest["mcp_server_version"]),
        "src/getbible_mcp/__init__.py": package_match.group(1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="GitHub release tag, normally vMAJOR.MINOR.PATCH")
    args = parser.parse_args()

    expected = normalized_tag(args.tag)
    versions = declared_versions()
    mismatches = {source: version for source, version in versions.items() if version != expected}
    if mismatches:
        print(f"Release tag resolves to {expected!r}, but version declarations differ:", file=sys.stderr)
        for source, version in mismatches.items():
            print(f"- {source}: {version}", file=sys.stderr)
        return 1

    print(f"Release version {expected} is consistent across {len(versions)} declarations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
