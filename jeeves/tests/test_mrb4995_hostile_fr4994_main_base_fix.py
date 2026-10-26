"""Hostile pin for FR #4994 / MRB #4995: main-base mrb-fix resync needles.

Pins contiguous log phrases and helpers so a later keep-both cannot drop the
FR #4994 carve-out that breaks the FIX-linked + skipped-fix deadlock.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
GITCLAIM = (ROOT / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")


def test_helpers_and_log_needles_contiguous():
    assert "def pr_base_ref(" in GITCLAIM
    assert "def mrb_fix_targets_default_branch(" in GITCLAIM
    assert 'return ref in ("main", "master")' in GITCLAIM
    assert "resync queue main-base mrb-fix PR" in GITCLAIM
    assert "resync skip twin mrb-fix PR" in GITCLAIM
    assert "main_base_fix_keeper" in GITCLAIM
    # Stacked (non-default) path must still skip while parent is open.
    assert "resync skip mrb-fix PR" in GITCLAIM
    assert "parent {parent} still open" in GITCLAIM


def test_master_is_default_branch_target():
    assert gitclaim.mrb_fix_targets_default_branch({"base": {"ref": "master"}})
    assert gitclaim.mrb_fix_targets_default_branch({"base": {"ref": "MAIN"}})
    assert not gitclaim.mrb_fix_targets_default_branch({"base": {"ref": "fix/mrb-11"}})
    assert not gitclaim.mrb_fix_targets_default_branch({})
