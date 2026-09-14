from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

COMMIT = "a" * 40


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_REPOSITORY", "getbible/mcp")
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setattr(sys, "argv", ["verify_main_merge.py", "--output", str(tmp_path / "output")])
    return importlib.import_module("verify_main_merge")


def merged_pr() -> dict[str, Any]:
    return {
        "number": 47, "state": "closed", "merged_at": "2026-09-14T15:00:00Z",
        "merge_commit_sha": COMMIT,
        "base": {"ref": "main", "repo": {"full_name": "getbible/mcp"}},
    }


def test_merge_gate_accepts_the_final_merge_commit_on_a_later_page(gate: ModuleType) -> None:
    associated = {**merged_pr(), "merge_commit_sha": "b" * 40}
    assert gate.merged_pull_request([[associated], [merged_pr()]], COMMIT) == 47


@pytest.mark.parametrize("change", [
    {"state": "open"}, {"merged_at": None}, {"merged_at": ""},
    {"merge_commit_sha": "b" * 40},
    {"base": {"ref": "release", "repo": {"full_name": "getbible/mcp"}}},
    {"base": {"ref": "main", "repo": {"full_name": "someone/mcp"}}},
    {"base": None}, {"number": None},
])
def test_association_alone_does_not_authorize_publication(
    gate: ModuleType, change: dict[str, Any],
) -> None:
    assert gate.merged_pull_request([[{**merged_pr(), **change}]], COMMIT) is None


@pytest.mark.parametrize(("key", "value"), [
    ("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_EVENT_NAME", "workflow_dispatch"),
    ("GITHUB_REF", "refs/heads/release"),
    ("GITHUB_REF", "refs/tags/v2.0.2"),
    ("GITHUB_REPOSITORY", "someone/mcp"),
])
def test_other_events_never_contact_github_or_authorize_publication(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str, value: str,
) -> None:
    monkeypatch.setenv(key, value)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("An ineligible event must not query release authorization")

    monkeypatch.setattr(gate.subprocess, "run", forbidden)
    assert gate.main() == 0
    assert (tmp_path / "output").read_text() == "allowed=false\n"


@pytest.mark.parametrize("merged", [False, True])
def test_main_push_requires_confirmed_merged_pr(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, merged: bool,
) -> None:
    def response(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == [
            "gh", "api", "--paginate", "--slurp",
            f"repos/getbible/mcp/commits/{COMMIT}/pulls?per_page=100",
        ]
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0, json.dumps([[merged_pr()] if merged else []]))

    monkeypatch.setattr(gate.subprocess, "run", response)
    assert gate.main() == 0
    assert (tmp_path / "output").read_text() == f"allowed={str(merged).lower()}\n"


@pytest.mark.parametrize("payload", ["not-json", "{}", "[]", '[{"number": 47}]', '[[null]]'])
def test_invalid_github_response_fails_without_authorizing(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: str,
) -> None:
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, payload))
    assert gate.main() == 1
    assert not (tmp_path / "output").exists()


def test_github_failure_fails_without_authorizing(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise subprocess.CalledProcessError(1, "gh api")

    monkeypatch.setattr(gate.subprocess, "run", unavailable)
    assert gate.main() == 1
    assert not (tmp_path / "output").exists()
