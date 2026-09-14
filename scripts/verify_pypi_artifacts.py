#!/usr/bin/env python3
"""Reject existing PyPI files that differ from the exact validated release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

from bump_version import VERSION
from release_state import optional_json


class PublicationPending(ValueError):
    """PyPI has not made all uploaded distribution metadata visible yet."""


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
            raise PublicationPending("PyPI has not returned the published version yet")
        return
    info = package.get("info")
    if not isinstance(info, dict) or info.get("version") != version or not isinstance(package.get("urls"), list):
        raise ValueError("Invalid PyPI release metadata")
    seen: set[str] = set()
    for published in package["urls"]:
        if not isinstance(published, dict):
            raise ValueError("Invalid PyPI release-file metadata")
        filename = published.get("filename")
        digests = published.get("digests")
        if not isinstance(digests, dict):
            raise ValueError("Invalid PyPI release-file checksums")
        digest = digests.get("sha256")
        if (
            not isinstance(filename, str) or filename not in artifacts or filename in seen
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
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
        raise PublicationPending("PyPI has not returned both validated distributions yet")


def verify_published_artifacts(
    directory: Path, version: str, *, require_complete: bool = False,
    attempts: int = 1, retry_delay: float = 10,
) -> None:
    """Retry only missing metadata; any identity or metadata error fails immediately."""
    if attempts < 1 or not math.isfinite(retry_delay) or retry_delay < 0:
        raise ValueError("Expected at least one attempt and a finite, nonnegative retry delay")
    for attempt in range(1, attempts + 1):
        package = optional_json(f"https://pypi.org/pypi/getbible-mcp/{version}/json")
        try:
            verify_artifacts(directory, version, package, require_complete=require_complete)
            return
        except PublicationPending:
            if attempt == attempts:
                raise
            print(
                f"PyPI metadata is not complete yet; checking again in {retry_delay:g} seconds "
                f"(attempt {attempt}/{attempts}).",
                flush=True,
            )
            time.sleep(retry_delay)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--attempts", type=int, default=1,
        help="Maximum metadata checks with --require-complete (default: 1)",
    )
    parser.add_argument(
        "--retry-delay", type=float, default=10,
        help="Seconds between incomplete metadata checks (default: 10)",
    )
    args = parser.parse_args()
    try:
        if VERSION.fullmatch(args.version) is None:
            raise ValueError("Expected a stable 2.MINOR.PATCH version")
        verify_published_artifacts(
            args.directory, args.version, require_complete=args.require_complete,
            attempts=args.attempts, retry_delay=args.retry_delay,
        )
        print("Every already-published file matches the validated release artifacts.")
        return 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Artifact verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
