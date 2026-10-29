"""docs/mrb-5168 hostile pins for FR #5163 / PR #5168."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines


def _idle_home(tmp_path, monkeypatch, nicks):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mids = {n.split("-")[0] for n in nicks}
    registered_machines.save_registered(tmp_path, mids)
    digest = bobreport.empty_digest()
    for nick in nicks:
        mid = nick.split("-")[0]
        digest["machines"].setdefault(mid, bobreport._empty_machine(mid))
        digest["machines"][mid].setdefault("worker_list", [])
        digest["machines"][mid]["worker_list"].append({"nick": nick, "state": "idle"})
    bobreport.save_digest(tmp_path, digest)


def test_author_is_never_in_clearable(tmp_path, monkeypatch):
    a, b = "flamingo-1", "marchhare-2"
    _idle_home(tmp_path, monkeypatch, [a, b])
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "id": "#1",
        "url": "https://github.com/SimonBarnett/a-search/pull/1",
        "author_seat": a,
        "giveup_seats": f"{a},{b}",
        "needs_human": False,
    }
    info = gitclaim.detect_mrb_reviewer_deadlock(
        tmp_path,
        idle={a, b},
        live={a, b},
        rows=[row],
        ledger={},
    )
    assert info is not None
    for _r, nick in info.get("clearable") or []:
        assert nick.lower() != a.lower()


def test_fr_only_queue_is_not_deadlock(tmp_path, monkeypatch):
    a = "flamingo-1"
    _idle_home(tmp_path, monkeypatch, [a])
    rows = [
        {
            "task": "FR",
            "repo": "SimonBarnett/bobiverse",
            "id": "#2",
            "url": "https://github.com/SimonBarnett/bobiverse/issues/2",
            "author_seat": a,
        }
    ]
    assert (
        gitclaim.detect_mrb_reviewer_deadlock(
            tmp_path, idle={a}, live={a}, rows=rows, ledger={}
        )
        is None
    )
