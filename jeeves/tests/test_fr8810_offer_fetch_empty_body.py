"""FR #8810 / BOB-D6: offer_focus_top hydrates empty FR body before depends gate."""
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
    # Isolate BOB-D6 shared body-fetch TTL across tests (empty negative-cache flake).
    if hasattr(gitclaim, "FR_BODY_FETCH_SHARED_CACHE"):
        gitclaim.FR_BODY_FETCH_SHARED_CACHE.clear()
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
        "body": "",
    }
    r.update(kw)
    return r


def test_fr8810_empty_body_with_open_depend_is_not_silent_offer(home: Path):
    """S1 fail-when: empty body must fetch; Depends-on OPEN then skips (not silent offer)."""
    me = "marchhare-35600"
    dep = _row(5, 1, body="Depends-on: (none)\n")
    dep["nick"] = "marchhare-35601"
    dep["accepted_ts"] = "2026-10-01T10:00:00Z"
    blocked = _row(3, 2, body="")  # empty — stamp only on GitHub
    later = _row(9, 3, body="Depends-on: (none)\n")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [blocked, later], "accepted": [dep], "done": [], "workers": {}},
    )
    fi.handle_focus_cmd(home, REPO)

    calls: list[tuple[str, str]] = []

    def fetch_issue(repo: str, num: str) -> dict:
        calls.append((repo, str(num)))
        if str(num) == "3":
            return {"number": 3, "body": "Depends-on: #5\n", "state": "open"}
        return {"number": int(num), "body": "Depends-on: (none)\n", "state": "open"}

    st, job = gitclaim.offer_focus_top(
        home, me, "#marchhare", fetch_issue=fetch_issue
    )
    assert (REPO, "3") in calls
    assert st == "ok" and job is not None
    assert job["id"] == "#9"  # #3 blocked after hydrate; #9 offered
    doc = gitclaim.load_queue(home)
    row3 = next(r for r in doc["unaccepted"] if r.get("id") == "#3")
    assert "Depends-on: #5" in str(row3.get("body") or "")
    assert not str(row3.get("offered_to") or "").strip()


def test_fr8810_empty_body_without_depends_still_offerable(home: Path):
    me = "marchhare-35600"
    row = _row(11, 1, body="")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": [], "workers": {}},
    )
    fi.handle_focus_cmd(home, REPO)

    def fetch_issue(repo: str, num: str) -> dict:
        return {"number": 11, "body": "No depends here.\n", "state": "open"}

    st, job = gitclaim.offer_focus_top(
        home, me, "#marchhare", fetch_issue=fetch_issue
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#11"
