"""FR #4606: Sync tip heal for gitclaim.py + RelPath allows *.py."""
from __future__ import annotations

from pathlib import Path


def _common_scripts() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts"


def test_common_ps1_allows_py_relpath_and_gitclaim_sync():
    text = (_common_scripts() / "Bobiverse-Common.ps1").read_text(encoding="utf-8")
    assert r"\.(ps1|py)$" in text or ".(ps1|py)" in text
    assert "function Sync-BobiverseGitclaimFromOrigin" in text
    assert "common/scripts/gitclaim.py" in text
    assert "FR #4606" in text


def test_sync_from_repo_calls_gitclaim_heal():
    text = (_common_scripts() / "Sync-BobiverseFromRepo.ps1").read_text(encoding="utf-8")
    assert "Sync-BobiverseGitclaimFromOrigin" in text
    assert "sync-gitclaim-from-tip" in text
