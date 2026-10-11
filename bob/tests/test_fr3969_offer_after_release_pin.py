"""FR #3969: mrb2832 source pin follows offer_after_release after #3895.

#3895 moved offer_focus_top into offer_after_release; offer_after_giveup is a
thin wrapper. The hostile pin must not look only inside the wrapper body.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"


def test_fr3969_offer_after_giveup_delegates_to_release():
    text = GITCLAIM.read_text(encoding="utf-8")
    i = text.index("def offer_after_giveup")
    chunk = text[i : i + 700]
    assert "return offer_after_release(" in chunk
    assert 'offered_via="giveup"' in chunk


def test_fr3969_offer_after_release_calls_offer_focus_top():
    text = GITCLAIM.read_text(encoding="utf-8")
    i = text.index("def offer_after_release")
    chunk = text[i : i + 900]
    assert "offer_focus_top" in chunk
    assert "offered_via" in chunk
