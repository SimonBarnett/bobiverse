"""FR #9489: interim MRB author heal nick ghost-N sticks; enrich does not recover real implementer."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _doc_with_done_fr_implementer(*, impl: str = "flamingo-17068") -> dict:
    return {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9271",
                "nick": impl,
                "done_by": impl,
                "url": "https://github.com/SimonBarnett/bobiverse/pull/9450",
                "ts": "t",
                "line": "DONE FR",
            }
        ],
    }


def test_canon_seat_nick_accepts_reserved_ghost_heal():
    assert gitclaim._canon_seat_nick("ghost-1") == "ghost-1"
    assert gitclaim._canon_seat_nick("GHOST-99") == "ghost-99"
    assert gitclaim._canon_seat_nick("ghost-") == ""
    assert gitclaim._canon_seat_nick("ghost-0") == ""
    assert gitclaim._canon_seat_nick("ghost-x") == ""


def test_enrich_keeps_ghost_heal_and_skips_done_fr_recover(tmp_path, monkeypatch):
    """Operator stamp ghost-1 must stick; flamingo DONE-FR implementer must not return."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare", "redqueen"})
    doc = _doc_with_done_fr_implementer()
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9450",
        "author_seat": "ghost-1",
        "implementer_seat": "ghost-1",
        "title": "FR #9271 Plan click",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9450",
    }
    out = gitclaim.enrich_mrb_author_fields(doc, row)
    assert out.get("author_seat") == "ghost-1"
    assert out.get("implementer_seat") == "ghost-1"
    assert "flamingo-17068" not in gitclaim.row_author_seats(out)
    assert gitclaim.row_author_seats(out) == ["ghost-1"]


def test_enrich_keeps_roster_dead_pid_heal(tmp_path, monkeypatch):
    """Documented interim heal: <roster-machine>-<dead-pid> stays parseable and sticky."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare", "redqueen"})
    doc = _doc_with_done_fr_implementer()
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9450",
        "author_seat": "marchhare-99999",
        "implementer_seat": "marchhare-99999",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9450",
    }
    out = gitclaim.enrich_mrb_author_fields(doc, row)
    assert out.get("author_seat") == "marchhare-99999"
    assert out.get("implementer_seat") == "marchhare-99999"
    seats = gitclaim.row_author_seats(out)
    assert "marchhare-99999" in seats
    assert "flamingo-17068" not in seats


def test_enrich_still_recovers_when_author_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    doc = _doc_with_done_fr_implementer()
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9450",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9450",
    }
    out = gitclaim.enrich_mrb_author_fields(doc, row)
    assert out.get("author_seat") == "flamingo-17068"
    assert out.get("implementer_seat") == "flamingo-17068"
