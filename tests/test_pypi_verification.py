from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.4.7"


@pytest.fixture
def verifier(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    module = importlib.import_module("verify_pypi_artifacts")
    monkeypatch.setattr(module.time, "sleep", Mock())
    return module


@pytest.fixture
def package(tmp_path: Path) -> dict[str, Any]:
    published = []
    for filename, content in (
        (f"getbible_mcp-{VERSION}-py3-none-any.whl", b"validated wheel"),
        (f"getbible_mcp-{VERSION}.tar.gz", b"validated source"),
    ):
        (tmp_path / filename).write_bytes(content)
        published.append({
            "filename": filename, "digests": {"sha256": hashlib.sha256(content).hexdigest()},
        })
    return {"info": {"version": VERSION}, "urls": published}


def test_publication_waits_for_both_exact_distribution_identities(
    verifier: ModuleType, package: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial = {**package, "urls": package["urls"][:1]}
    fetch = Mock(side_effect=[None, partial, package])
    monkeypatch.setattr(verifier, "optional_json", fetch)

    verifier.verify_published_artifacts(
        tmp_path, VERSION, require_complete=True, attempts=3, retry_delay=7,
    )

    assert fetch.call_count == 3
    fetch.assert_called_with(f"https://pypi.org/pypi/getbible-mcp/{VERSION}/json")
    assert verifier.time.sleep.call_args_list == [((7,),), ((7,),)]


@pytest.mark.parametrize("partial", [False, True])
def test_invisible_publication_exhausts_the_bound_and_fails(
    verifier: ModuleType, package: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, partial: bool,
) -> None:
    metadata = {**package, "urls": package["urls"][:1]} if partial else None
    fetch = Mock(return_value=metadata)
    monkeypatch.setattr(verifier, "optional_json", fetch)

    with pytest.raises(verifier.PublicationPending, match="PyPI has not returned"):
        verifier.verify_published_artifacts(
            tmp_path, VERSION, require_complete=True, attempts=3, retry_delay=7,
        )

    assert fetch.call_count == 3
    assert verifier.time.sleep.call_count == 2


@pytest.mark.parametrize(
    "invalid", ["checksum", "filename", "duplicate", "info", "urls", "file", "digests"],
)
def test_mismatched_or_malformed_metadata_is_never_retried(
    verifier: ModuleType, package: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, invalid: str,
) -> None:
    broken = copy.deepcopy(package)
    if invalid == "checksum":
        broken["urls"][0]["digests"]["sha256"] = "0" * 64
    elif invalid == "filename":
        broken["urls"][0]["filename"] = "unexpected.whl"
    elif invalid == "duplicate":
        broken["urls"].append(broken["urls"][0])
    elif invalid == "info":
        broken["info"] = None
    elif invalid == "urls":
        broken["urls"] = None
    elif invalid == "file":
        broken["urls"][0] = None
    elif invalid == "digests":
        broken["urls"][0]["digests"] = None
    fetch = Mock(side_effect=[None, broken, package])
    monkeypatch.setattr(verifier, "optional_json", fetch)

    with pytest.raises(ValueError) as error:
        verifier.verify_published_artifacts(
            tmp_path, VERSION, require_complete=True, attempts=3,
        )

    assert not isinstance(error.value, verifier.PublicationPending)
    assert fetch.call_count == 2
    verifier.time.sleep.assert_called_once_with(10)


def test_network_failure_is_not_mistaken_for_delayed_publication(
    verifier: ModuleType, package: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = Mock(side_effect=HTTPError("https://pypi.org/", 503, "Unavailable", {}, None))
    monkeypatch.setattr(verifier, "optional_json", fetch)

    with pytest.raises(HTTPError):
        verifier.verify_published_artifacts(tmp_path, VERSION, require_complete=True, attempts=3)

    fetch.assert_called_once()
    verifier.time.sleep.assert_not_called()


@pytest.mark.parametrize("partial", [False, True])
def test_preflight_allows_missing_files_without_waiting(
    verifier: ModuleType, package: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, partial: bool,
) -> None:
    metadata = {**package, "urls": package["urls"][:1]} if partial else None
    fetch = Mock(return_value=metadata)
    monkeypatch.setattr(verifier, "optional_json", fetch)

    verifier.verify_published_artifacts(tmp_path, VERSION, attempts=3)

    fetch.assert_called_once()
    verifier.time.sleep.assert_not_called()


@pytest.mark.parametrize(
    ("attempts", "delay"), [(0, 10), (-1, 10), (1, -1), (1, float("inf")), (1, float("nan"))],
)
def test_invalid_retry_settings_fail_before_network_access(
    verifier: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    attempts: int, delay: float,
) -> None:
    fetch = Mock()
    monkeypatch.setattr(verifier, "optional_json", fetch)

    with pytest.raises(ValueError, match="at least one attempt"):
        verifier.verify_published_artifacts(
            tmp_path, VERSION, require_complete=True, attempts=attempts, retry_delay=delay,
        )

    fetch.assert_not_called()
    verifier.time.sleep.assert_not_called()


def test_command_reports_failure_after_configured_attempts(
    verifier: ModuleType, package: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    fetch = Mock(return_value=None)
    monkeypatch.setattr(verifier, "optional_json", fetch)
    monkeypatch.setattr("sys.argv", [
        "verify_pypi_artifacts.py", VERSION, str(tmp_path),
        "--require-complete", "--attempts", "2", "--retry-delay", "7",
    ])

    assert verifier.main() == 1

    assert fetch.call_count == 2
    verifier.time.sleep.assert_called_once_with(7)
    output = capsys.readouterr()
    assert "Artifact verification failed" in output.err
    assert "Every already-published file matches" not in output.out
