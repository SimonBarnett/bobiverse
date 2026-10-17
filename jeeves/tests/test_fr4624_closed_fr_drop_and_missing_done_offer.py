"""FR #4624: closed-issue FR must leave the offer queue; missing DONE still pushes next job.

Regression of #2340 / #2496: after ``issues closed``, seats kept ACK'ing a-search#3355
because (1) accepted rows were not stamped closed and returned to unaccepted on seat
depart without a stamp, and (2) DONE status=missing skipped done-offer (FR #4089)
so the seat sat idle while other work was queued.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import shop_listen
from gitclaim import GitClaim, apply_queue_event, load_unaccepted


REPO = "SimonBarnett/a-search"
IRC = Path(__file__).resolve().parents[2] / "common" / "scripts" / "irc_agent.py"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _fr_row(ident: str = "#3355", *, state: str = "open", **extra) -> dict:
    row = {
        "task": "FR",
        "repo": REPO,
        "id": ident,
        "title": "closed twin",
        "url": f"https://github.com/{REPO}/issues/{ident.lstrip('#')}",
        "line": f"FR {ident}",
        "state": state,
        "seq": 1,
    }
    row.update(extra)
    return row


def test_closed_event_drops_unaccepted_fr(tmp_path: Path):
    home = _home(tmp_path)
    apply_queue_event(
        home,
        GitClaim(
            repo=REPO,
            task="FR",
            id="#3355",
            event="issues",
            action="opened",
            line="l",
            title="x",
            state="open",
        ),
    )
    assert ("FR", "#3355") in [(r["task"], r["id"]) for r in load_unaccepted(home)]
    changed = apply_queue_event(
        home,
        GitClaim(
            repo=REPO,
            task="FR",
            id="#3355",
            event="issues",
            action="closed",
            line="l",
            state="closed",
        ),
    )
    assert changed in ("removed", "updated")
    assert load_unaccepted(home) == []


def test_closed_event_stamps_accepted_fr_state_closed(tmp_path: Path):
    """Holding seat keeps ACC until DONE, but state=closed so release cannot re-offer."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                _fr_row(
                    nick="marchhare-13128",
                    accepted_by="marchhare-13128",
                    channel="#marchhare",
                )
            ],
            "done": [],
        },
    )
    changed = apply_queue_event(
        home,
        GitClaim(
            repo=REPO,
            task="FR",
            id="#3355",
            event="issues",
            action="closed",
            line="l",
            state="closed",
        ),
    )
    assert changed != "noop"
    doc = gitclaim._load_queue_unlocked(home)
    assert len(doc["accepted"]) == 1
    assert doc["accepted"][0]["state"] == "closed"
    assert doc["unaccepted"] == []


def test_release_closed_accepted_fr_goes_to_done_not_unaccepted(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    gone = "flamingo-63220"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                _fr_row(
                    state="closed",
                    nick=gone,
                    accepted_by=gone,
                    channel="#flamingo",
                )
            ],
            "done": [],
        },
    )
    released = gitclaim.release_accepted_for_departed_nick(home, gone)
    # Not re-offerable: either empty release list or rows that did not re-enter unaccepted.
    doc = gitclaim._load_queue_unlocked(home)
    assert doc["accepted"] == []
    assert not any(
        r.get("id") == "#3355" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("unaccepted") or [])
    )
    assert any(
        r.get("id") == "#3355"
        and str(r.get("task") or "").upper() == "FR"
        and str(r.get("result") or "").upper() == "CLOSED"
        for r in (doc.get("done") or [])
    )
    assert not any(
        r.get("id") == "#3355" and str(r.get("state") or "").lower() != "closed"
        for r in released
        if isinstance(r, dict)
    )


def test_resync_never_readds_closed_issue(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_fr_row(state="open")],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            return []  # closed — absent from open list
        if "/pulls?" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch)
    doc = gitclaim._load_queue_unlocked(home)
    assert not any(
        r.get("id") == "#3355" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("unaccepted") or [])
    )


def test_done_after_closed_accepted_clears_row(tmp_path: Path):
    home = _home(tmp_path)
    nick = "marchhare-13128"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                _fr_row(
                    state="closed",
                    nick=nick,
                    accepted_by=nick,
                    channel="#marchhare",
                )
            ],
            "done": [],
        },
    )
    st, job = shop_listen.complete_job_by_ref(
        home,
        nick=nick,
        repo=REPO,
        task="FR",
        ident="#3355",
        result="",
        url="https://github.com/SimonBarnett/a-search/pull/2075",
    )
    assert st == "ok" and job is not None
    doc = gitclaim._load_queue_unlocked(home)
    assert doc["accepted"] == []
    assert not any(r.get("id") == "#3355" for r in (doc.get("unaccepted") or []))


def test_irc_agent_done_missing_still_triggers_done_offer():
    """FR #4624: status=missing (ACC already dropped) must still call offer_after_done."""
    src = IRC.read_text(encoding="utf-8")
    assert "FR #4624" in src or "status == \"missing\"" in src
    # Must not skip all non-ok DONE paths forever.
    skip_at = src.find("done-offer skipped")
    assert skip_at > 0
    window = src[max(0, skip_at - 400) : skip_at + 200]
    # missing must be handled as an offer path, not only logged-and-skipped.
    assert 'status == "missing"' in src or 'status in ("ok", "missing")' in src
    assert "offer_after_done" in src
    # The old FR #4089 gate that skipped every non-ok DONE must be gone.
    assert 'elif verb == "DONE" and status != "ok":' not in src


def test_claim_from_payload_closed_carries_state_closed():
    payload = {
        "action": "closed",
        "repository": {"full_name": REPO},
        "issue": {
            "number": 3355,
            "title": "dup",
            "body": "Duplicate of #1343",
            "state": "closed",
            "labels": [{"name": "feature-request"}],
        },
    }
    c = gitclaim.claim_from_payload("issues", payload)
    assert c is not None
    assert c.action == "closed"
    assert str(c.state or "").lower() == "closed"
