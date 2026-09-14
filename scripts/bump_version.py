#!/usr/bin/env python3
"""Read or increment the coordinated GetBible MCP 2.x package version."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from verify_release import ROOT, declared_versions

VERSION = re.compile(r"2\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def current_version(root: Path = ROOT) -> str:
    versions = declared_versions(root)
    values = set(versions.values())
    if len(values) != 1:
        raise ValueError(f"Package version declarations differ: {versions}")
    version = values.pop()
    if VERSION.fullmatch(version) is None:
        raise ValueError("Automated releases require a stable 2.MINOR.PATCH package version")
    return version


def bump_patch(root: Path = ROOT) -> str:
    """Validate every declaration before replacing any version file."""
    previous = current_version(root)
    major, minor, patch = previous.split(".")
    updated = f"{major}.{minor}.{int(patch) + 1}"
    replacements: dict[Path, str] = {}
    for relative, pattern in (
        ("pyproject.toml", r'^version\s*=\s*"' + re.escape(previous) + r'"$'),
        ("src/getbible_mcp/__init__.py", r'^__version__\s*=\s*"' + re.escape(previous) + r'"$'),
    ):
        path = root / relative
        original = path.read_text(encoding="utf-8")
        new_text, count = re.subn(
            pattern,
            lambda match: match.group().replace(previous, updated),
            original,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError(f"Expected exactly one package version declaration in {relative}")
        replacements[path] = new_text
    for relative, key in (
        ("server.json", "version"),
        ("site/v2/manifest.json", "mcp_server_version"),
        ("site/manifest.json", "package_version"),
    ):
        path = root / relative
        document = json.loads(path.read_text(encoding="utf-8"))
        document[key] = updated
        if relative == "server.json":
            for package in document["packages"]:
                package["version"] = updated
        replacements[path] = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    for path, content in replacements.items():
        temporary = path.with_name(path.name + ".version.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", action="store_true", help="Print the consistent version only")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        print(current_version(args.root) if args.current else bump_patch(args.root))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Unable to determine package version: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
