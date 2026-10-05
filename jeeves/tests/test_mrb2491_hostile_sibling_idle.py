"""MRB #2491 hostile gates: sibling idle viability + free_seat wire."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import pytest


@pytest.fixture(autouse=True)
def _roster(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(
        tmp_path, {"ionos", "win-mpre8vi4u6u", "marchhare"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def test_mrb2491_offer_and_assign_source_pass_free():
    src = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "free_seat_nicks" in src
    assert "FR #2487" in src
    # Both offer paths must pass free= into review_blocked_for_author.
    assert src.count("free=free") >= 2


def test_mrb2491_exact_author_always_blocked_even_if_others_busy():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#2491",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/2491",
        "author_seat": "marchhare-35016",
        "implementer_seat": "marchhare-35016",
    }
    live = {"marchhare-35016", "marchhare-40208", "win-mpre8vi4u6u-14452"}
    free = {"marchhare-35016", "marchhare-40208"}  # other machine busy
    assert gitclaim.review_blocked_for_author(row, "marchhare-35016", live, free=free) is True
