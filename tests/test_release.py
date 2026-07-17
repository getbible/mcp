from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_RELEASE = ROOT / "scripts/verify_release.py"


def test_release_versions_match_v1_tag() -> None:
    result = subprocess.run(
        [sys.executable, str(VERIFY_RELEASE), "v1.0.0"],
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
