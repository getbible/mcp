#!/usr/bin/env python3
"""Plan an idempotent release without creating tags, releases or package uploads."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bump_version import current_version
from verify_release import ROOT, normalized_tag


def optional_json(url: str, token: str | None = None) -> dict[str, Any] | None:
    headers = {"Accept": "application/json", "User-Agent": "getbible-mcp-release"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            document = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(document, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return document


def release_plan(
    version: str,
    commit: str,
    tag_commit: str | None,
    published: bool,
    release_exists: bool,
) -> dict[str, str]:
    """Existing tags pin retries; package existence never causes a duplicate upload."""
    return {
        "version": version,
        "tag": f"v{version}",
        "ref": tag_commit or commit,
        "needed": str(not (tag_commit and published and release_exists)).lower(),
        "publish": str(not published).lower(),
        "create_tag": str(tag_commit is None).lower(),
        "create_release": str(not release_exists).lower(),
    }


def package_complete(package: dict[str, Any] | None, version: str) -> bool:
    """A wheel-only partial upload must not masquerade as a completed release."""
    if package is None:
        return False
    if package.get("info", {}).get("version") != version:
        raise ValueError("PyPI returned metadata for an unexpected version")
    artifacts = package.get("urls")
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        raise ValueError("PyPI returned invalid release-file metadata")
    kinds = {item.get("packagetype") for item in artifacts}
    return {"bdist_wheel", "sdist"}.issubset(kinds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="", help="Optional tag; must match the selected package version")
    parser.add_argument("--commit", required=True, help="The main commit being considered")
    parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    parser.add_argument("--output", type=Path, help="GitHub Actions output file")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{40,64}", args.commit):
            raise ValueError("Expected a full immutable commit SHA")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            raise ValueError("Expected a GitHub owner/repository name")
        version = current_version()
        if args.tag and normalized_tag(args.tag) != version:
            raise ValueError("The requested release tag does not match the selected package version")
        tag = f"v{version}"
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        if result.returncode not in {0, 1}:
            raise ValueError(f"Unable to inspect Git tag: {result.stderr.strip()}")
        tag_commit = result.stdout.strip() if result.returncode == 0 else None
        package = optional_json(f"https://pypi.org/pypi/getbible-mcp/{version}/json")
        published = package_complete(package, version)
        release = optional_json(
            f"https://api.github.com/repos/{args.repository}/releases/tags/{tag}",
            os.environ.get("GH_TOKEN"),
        )
        if release is not None and release.get("tag_name") != tag:
            raise ValueError("GitHub returned an unexpected release tag")
        plan = release_plan(version, args.commit, tag_commit, published, release is not None)
        lines = "".join(f"{key}={value}\n" for key, value in plan.items())
        if args.output:
            with args.output.open("a", encoding="utf-8") as output:
                output.write(lines)
        print(lines, end="")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"Unable to plan release: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
