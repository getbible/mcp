#!/usr/bin/env python3
"""Reject existing PyPI files that differ from the exact validated release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

from bump_version import VERSION
from release_state import optional_json


def verify_artifacts(
    directory: Path, version: str, package: dict[str, Any] | None, *, require_complete: bool = False,
) -> None:
    artifacts = {path.name: path for path in directory.iterdir() if path.is_file()}
    expected = {
        f"getbible_mcp-{version}-py3-none-any.whl",
        f"getbible_mcp-{version}.tar.gz",
    }
    if set(artifacts) != expected:
        raise ValueError("Expected exactly the validated wheel and source distribution")
    if package is None:
        if require_complete:
            raise ValueError("PyPI has not returned the published version yet; retry publication")
        return
    if package.get("info", {}).get("version") != version or not isinstance(package.get("urls"), list):
        raise ValueError("Invalid PyPI release metadata")
    seen: set[str] = set()
    for published in package["urls"]:
        if not isinstance(published, dict):
            raise ValueError("Invalid PyPI release-file metadata")
        filename = published.get("filename")
        digest = published.get("digests", {}).get("sha256")
        if filename not in artifacts or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Unexpected published artifact or checksum: {filename}")
        with artifacts[filename].open("rb") as artifact:
            actual = hashlib.file_digest(artifact, "sha256").hexdigest()
        if actual != digest:
            raise ValueError(
                f"Published {filename} differs from the validated artifact. "
                "Recover the original validated distributions or publish a new version; "
                "never combine different builds under one version."
            )
        seen.add(filename)
    if require_complete and seen != expected:
        raise ValueError("PyPI has not returned both validated distributions yet; retry publication")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        if VERSION.fullmatch(args.version) is None:
            raise ValueError("Expected a stable 2.MINOR.PATCH version")
        package = optional_json(f"https://pypi.org/pypi/getbible-mcp/{args.version}/json")
        verify_artifacts(args.directory, args.version, package, require_complete=args.require_complete)
        print("Every already-published file matches the validated release artifacts.")
        return 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Artifact verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
