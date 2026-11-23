"""FR #8808 / BOB-D4: offer_focus_top offers FR after Depends-on flips CLOSED."""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-35600",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-17T12:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(num: int, seq: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def test_fr8808_offer_after_depend_state_closed(home: Path):
    """S1 flip: OPEN depend skips; state=closed on depend then offers the blocked FR."""
    me = "marchhare-35600"
    dep = _row(5, 1)
    dep["nick"] = "marchhare-35601"
    dep["accepted_ts"] = "2026-10-01T10:00:00Z"
    blocked = _row(3, 2, body="Depends-on: #5\n")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [blocked], "accepted": [dep], "done": [], "workers": {}},
    )
    fi.handle_focus_cmd(home, REPO)

    st1, job1 = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st1 == "empty" and job1 is None

    # Flip depend CLOSED in accepted (still present, no longer in open_fr_issue_keys).
    with gitclaim._lock(home):
        doc = gitclaim._load_queue_unlocked(home)
        for r in doc.get("accepted") or []:
            if str(r.get("id")) == "#5":
                r["state"] = "closed"
        gitclaim._write_queue(gitclaim.queue_path(home), doc)

    st2, job2 = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st2 == "ok" and job2 is not None
    assert job2["id"] == "#3"