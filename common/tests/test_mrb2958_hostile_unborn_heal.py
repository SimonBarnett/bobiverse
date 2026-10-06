"""Hostile pins for MRB #2958 / FR #2944 unborn install HEAD heal.

Product already on main via #2958. Pins Sync-BobiverseWorkTree heal phrases and
post-install docs so a later wipe cannot drop the empty-master repair playbook.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "scripts" / "Bobiverse-Common.ps1"
DOCS = ROOT / "docs" / "post-install.md"
PRODUCT = ROOT / "tests" / "test_worktree_sync_020.py"


def _text(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    assert not t.startswith("\ufeff")
    assert t.endswith("\n")
    return t


def test_mrb2958_common_pins_unborn_heal():
    text = _text(COMMON)
    assert "FR #2944" in text
    assert "worktree-heal-unborn" in text
    assert "rev-parse" in text and "HEAD" in text
    # Heal block must checkout -B Branch --track origin/Branch after sparse set.
    idx = text.find("FR #2944")
    assert idx > 0
    window = text[idx : idx + 1800]
    assert "sparse-checkout" in window
    assert "checkout" in window and "--track" in window
    assert "KEEP_BRANCH" in window or "empty HEAD is not agent work" in window


def test_mrb2958_post_install_docs_note():
    text = _text(DOCS)
    assert "FR #2944" in text
    assert "No commits yet" in text
    assert "worktree-heal-unborn" in text
    assert "origin/main" in text or "main" in text


def test_mrb2958_product_test_present():
    text = _text(PRODUCT)
    assert "test_fr2944_unborn_empty_master_heals_to_main" in text
    assert "worktree-heal-unborn" in text
