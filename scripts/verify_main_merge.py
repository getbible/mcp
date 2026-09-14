#!/usr/bin/env python3
"""Allow production publication only for a PR merge pushed to the official main branch."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY = "getbible/mcp"


def merged_pull_request(pages: Any, commit: str) -> int | None:
    """Match the final merge, squash or rebase commit, not merely an associated PR."""
    if not isinstance(pages, list) or not pages or any(
        not isinstance(page, list) or any(not isinstance(pr, dict) for pr in page)
        for page in pages
    ):
        raise ValueError("GitHub returned invalid pull-request metadata")
    for page in pages:
        for pr in page:
            base = pr.get("base") or {}
            repository = base.get("repo") or {}
            if (
                pr.get("state") == "closed"
                and isinstance(pr.get("merged_at"), str)
                and pr["merged_at"]
                and pr.get("merge_commit_sha") == commit
                and base.get("ref") == "main"
                and repository.get("full_name") == REPOSITORY
                and type(pr.get("number")) is int
                and pr["number"] > 0
            ):
                return int(pr["number"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="GitHub Actions output file")
    args = parser.parse_args()
    try:
        eligible = (
            os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/main"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        )
        number = None
        if eligible:
            commit = os.environ.get("GITHUB_SHA", "")
            if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
                raise ValueError("Expected a full immutable commit SHA")
            response = subprocess.run(
                ["gh", "api", "--paginate", "--slurp",
                 f"repos/{REPOSITORY}/commits/{commit}/pulls?per_page=100"],
                check=True, capture_output=True, text=True, timeout=60,
            )
            number = merged_pull_request(json.loads(response.stdout), commit)
        with args.output.open("a", encoding="utf-8") as output:
            output.write(f"allowed={str(number is not None).lower()}\n")
        if number is None:
            print("No PR merge into getbible/mcp main at this commit; publication skipped.")
        else:
            print(f"Verified merged PR #{number} at the triggering main commit.")
        return 0
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        print(f"Unable to verify the release merge: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
