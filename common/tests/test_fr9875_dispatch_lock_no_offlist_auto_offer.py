"""FR #9875: tip/build-lock must not auto-offer off-list FRs; clear off-list ACC on tip assign."""
from __future__ import annotations

import sys
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dispatch_lock as dl  # noqa: E402

REPO = "SimonBarnett/bobiverse"
NICK = "redqueen-10552"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {
            "nick": NICK,
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-24T21:30:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _fr(num: int, seq: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-24T21:00:{num % 60:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "Depends-on: (none)\n",
        "labels": [],
    }
    r.update(kw)
    return r


def _mrb(num: int, seq: int, **kw) -> dict:
    r = _fr(
        num,
        seq,
        task="MRB",
        title=f"MRB tip {num}",
        event="pull_request",
        url=f"https://github.com/{REPO}/pull/{num}",
        line=f"MRB {REPO}#{num}",
        changed_files=["jeeves/tools/x.py", "common/scripts/y.py"],
        pull_url=f"https://github.com/{REPO}/pull/{num}",
        coderabbit="off",
        review="full",
    )
    r.update(kw)
    return r


def test_fr9875_lock_blocks_nested_digest_fr_9859(home: Path):
    """Fail-when: #9859-class off-list FR offered while build-jeeves lock on."""
    dl.set_build_jeeves(home, True)
    nested = _fr(9859, 1, title="nested digest child")
    assert dl.row_blocked_reason(home, nested) == "dispatch-lock:fr"
    tip = _mrb(9839, 2)
    assert dl.row_blocked_reason(home, tip) is None


def test_fr9875_offer_focus_top_skips_offlist_under_lock(home: Path, monkeypatch):
    dl.set_build_jeeves(home, True)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_fr(9859, 1), _mrb(9839, 2)],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda *_a, **_k: {NICK})
    st, job = gitclaim.offer_focus_top(home, NICK, "#redqueen", now=1_700_000_000.0)
    assert st == "ok"
    assert job is not None
    assert str(job.get("id") or "") in ("#9839", "9839")
    assert str(job.get("task") or "").upper() == "MRB"


def test_fr9875_clear_offlist_accepted_on_tip_assign(home: Path):
    """When tip MRB is accepted under lock, off-list ACC FR returns to unaccepted."""
    dl.set_build_jeeves(home, True)
    offlist = _fr(9859, 1)
    offlist["accepted_by"] = NICK
    offlist["nick"] = NICK
    tip = _mrb(9839, 2)
    tip["accepted_by"] = NICK
    tip["nick"] = NICK
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [offlist, tip],
            "done": [],
            "workers": {},
        },
    )
    cleared = dl.clear_off_list_accepted(home, nick=NICK)
    assert cleared >= 1
    doc = gitclaim.load_queue(home)
    acc_ids = {str(r.get("id") or "").lstrip("#") for r in (doc.get("accepted") or [])}
    unacc_ids = {str(r.get("id") or "").lstrip("#") for r in (doc.get("unaccepted") or [])}
    assert "9839" in acc_ids
    assert "9859" not in acc_ids
    assert "9859" in unacc_ids
