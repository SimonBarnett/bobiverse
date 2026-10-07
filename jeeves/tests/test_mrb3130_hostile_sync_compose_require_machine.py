"""Hostile pins for MRB bobiverse#3130 / FR #3129."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import REPO, ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402

JEEVES = REPO / "jeeves"


def test_mrb3130_docs_pin_file_exists():
    text = (JEEVES / "docs" / "mrb-3130.md").read_text(encoding="utf-8-sig")
    assert "Sync/compose" in text or "sync/compose" in text.lower()
    assert "bare" in text.lower() or "BobiverseFromRepo" in text
    assert "#3122" in text


def test_mrb3130_bare_sync_still_unpinned_on_main():
    mid = gitclaim.infer_require_machine(
        title="hotpatch bob ear",
        body="Run Sync-BobiverseFromRepo -Product bob on marchhare.",
        labels=[],
        repo="SimonBarnett/bobiverse",
        ident="#1",
    )
    assert mid == ""


def test_mrb3130_hard_pin_3122_on_main():
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            labels=[],
            repo="SimonBarnett/bobiverse",
            ident="#3122",
        )
        == "ionos"
    )
