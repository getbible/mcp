#!/usr/bin/env python3
"""Check the reviewed OpenAPI snapshots against the nine published contracts.

Use --write to stage upstream changes for review. All downloads and request
contracts are validated before any snapshot is replaced. Normal MCP operation
and tests use the packaged snapshots and do not require a network connection.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import httpx
from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPIError
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

ROOT = Path(__file__).resolve().parents[1]
MAX_CONTRACT_BYTES = 10 * 1024 * 1024


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("OpenAPI JSON numbers must be finite")
    return number


def snapshot_paths(service: str, version: str) -> list[Path]:
    """Keep runtime resources and public versioned contracts aligned."""
    filename = f"{service}-{version}.json"
    return [
        ROOT / "src/getbible_mcp/openapi" / filename,
        ROOT / "site/contracts" / filename,
    ]


def download(client: httpx.Client, url: str) -> tuple[bytes, dict[str, Any]]:
    """Download one bounded JSON document without following redirects."""
    with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > MAX_CONTRACT_BYTES:
                raise ValueError(f"Contract exceeds {MAX_CONTRACT_BYTES} bytes: {url}")
    document = json.loads(content, parse_float=_finite_float, parse_constant=_finite_float)
    if not isinstance(document, dict):
        raise ValueError(f"Contract must be a JSON object: {url}")
    return bytes(content), document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Report drift without writing (default)")
    mode.add_argument("--write", action="store_true", help="Replace changed snapshots for review")
    args = parser.parse_args()

    # Prefer this checkout so the script also works before an editable install.
    sys.path.insert(0, str(ROOT / "src"))
    from getbible_mcp.contracts import CONTRACT_URLS, ContractRegistry, _check_references

    downloaded: dict[tuple[str, str], tuple[bytes, dict[str, Any]]] = {}
    try:
        with httpx.Client(timeout=30.0, follow_redirects=False, trust_env=False) as client:
            for key, url in CONTRACT_URLS.items():
                downloaded[key] = download(client, url)
        for key, (_, document) in downloaded.items():
            # Reject external references before a validator can resolve them.
            # Full OpenAPI validation also catches unknown path-item verbs and
            # malformed document structures the request adapter does not use.
            _check_references(document)
            try:
                validate(document)
            except (OpenAPIValidationError, OpenAPIError) as exc:
                raise ValueError(f"Invalid OpenAPI document for {key[0]}/{key[1]}: {exc}") from exc
        reviewed = ContractRegistry()
        updated = ContractRegistry({key: document for key, (_, document) in downloaded.items()})
        changed = [
            key
            for key, (_, document) in downloaded.items()
            if document != reviewed.document(*key)
            or any(
                not path.is_file() or path.read_bytes() != snapshot_paths(*key)[0].read_bytes()
                for path in snapshot_paths(*key)[1:]
            )
        ]
        old_operations = {
            (entry["service"], entry["version"]): {
                item["operation_id"] for item in entry["operations"]
            }
            for entry in reviewed.catalog()
        }
        new_operations = {
            (entry["service"], entry["version"]): {
                item["operation_id"] for item in entry["operations"]
            }
            for entry in updated.catalog()
        }
        for service, version in changed:
            old = old_operations[(service, version)]
            new = new_operations[(service, version)]
            print(f"Changed {service}/{version}: {len(old)} -> {len(new)} operations")
            if new - old:
                print(f"  Added: {', '.join(sorted(new - old))}")
            if old - new:
                print(f"  Removed: {', '.join(sorted(old - new))}")
        if not changed:
            print(f"All {len(CONTRACT_URLS)} reviewed contracts match the published APIs.")
            return 0
        if not args.write:
            print("Run with --write to update snapshots, then review the diff and run tests.")
            return 1
        for service, version in changed:
            for target in snapshot_paths(service, version):
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(".json.tmp")
                temporary.write_bytes(downloaded[(service, version)][0])
                temporary.replace(target)
        print(
            f"Updated {len(changed)} contract snapshots. Review the diff and run tests before committing."
        )
        return 0
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f"Unable to refresh contracts: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
