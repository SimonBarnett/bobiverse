"""FR #4851: issue closed while seat holds FR ACK -> shop CANCEL; digest stays busy; no auto-MRB."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import gitclaim
import shop_listen
from gitclaim import GitClaim, apply_queue_event


REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _fr_acc(ident: str = "#4439", *, nick: str = "marchhare-18680", **extra) -> dict:
    row = {
        "task": "FR",
        "repo": REPO,
        "id": ident,
        "title": "etsy credentials",
        "url": f"https://github.com/{REPO}/issues/{ident.lstrip('#')}",
        "line": f"FR {ident}",
        "state": "open",
        "nick": nick,
        "accepted_by": nick,
        "channel": "#marchhare",
        "seq": 1,
    }
    row.update(extra)
    return row


def test_format_cancel_line_wire():
    line = gitclaim.format_cancel_line(
        "marchhare-18680",
        {"task": "FR", "repo": REPO, "id": "#4439"},
        actor="SimonBarnett",
    )
    assert line == (
        f"marchhare-18680: CANCEL FR {REPO}#4439 (closed by SimonBarnett)"
    )
    bare = gitclaim.format_cancel_line(
        "flamingo-1",
        {"task": "FR", "repo": "o/r", "id": "7"},
    )
    assert bare == "flamingo-1: CANCEL FR o/r#7 (closed)"


def test_closed_event_enqueues_one_cancel_keeps_acc_and_digest(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    clear_calls = []

    def fake_clear(h, seat, only_if_work_contains=None):
        clear_calls.append((seat, only_if_work_contains))
        return mock.Mock(ok=True)

    monkeypatch.setattr(gitclaim.bobreport, "clear_seat_doing", fake_clear)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [_fr_acc()], "done": []},
    )
    changed = apply_queue_event(
        home,
        GitClaim(
            repo=REPO,
            task="FR",
            id="#4439",
            event="issues",
            action="closed",
            line="l",
            state="closed",
            actor="SimonBarnett",
        ),
    )
    assert changed != "noop"
    doc = gitclaim._load_queue_unlocked(home)
    assert len(doc["accepted"]) == 1
    acc = doc["accepted"][0]
    assert acc["state"] == "closed"
    assert acc.get("cancel_pending") is True
    assert clear_calls == []
    outbox = home / "chair-outbox.txt"
    assert outbox.is_file()
    text = outbox.read_text(encoding="utf-8")
    assert text.count("CANCEL FR") == 1
    assert "PRIVMSG #marchhare :" in text
    assert "marchhare-18680: CANCEL FR" in text
    assert "closed by SimonBarnett" in text


def test_purge_keeps_nick_held_closed_acc_no_clear(tmp_path, monkeypatch):
    home = _home(tmp_path)
    clear_calls = []

    def fake_clear(h, seat, only_if_work_contains=None):
        clear_calls.append((seat, only_if_work_contains))
        return mock.Mock(ok=True)

    monkeypatch.setattr(gitclaim.bobreport, "clear_seat_doing", fake_clear)
    doc = {
        "accepted": [
            _fr_acc(state="closed"),
            {
                "task": "FR",
                "repo": REPO,
                "id": "#99",
                "state": "closed",
                # orphan — no seat holder
            },
        ],
        "done": [],
    }
    n = gitclaim._purge_closed_fr_accepted(doc, home=home)
    assert n == 1  # orphan only
    assert [r["id"] for r in doc["accepted"]] == ["#4439"]
    assert doc["accepted"][0].get("cancel_pending") is True
    assert any(r.get("id") == "#99" and r.get("result") == "CLOSED" for r in doc["done"])
    assert clear_calls == []  # nick-held must not flip digest idle


def test_nack_cancel_pending_finalizes_done_closed(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    clear_calls = []

    def fake_clear(h, seat, only_if_work_contains=None):
        clear_calls.append((seat, only_if_work_contains))
        return mock.Mock(ok=True)

    monkeypatch.setattr(gitclaim.bobreport, "clear_seat_doing", fake_clear)
    nick = "marchhare-18680"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                _fr_acc(
                    nick=nick,
                    state="closed",
                    cancel_pending=True,
                    cancel_notified=True,
                )
            ],
            "done": [],
        },
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home, repo=REPO, task="FR", ident="#4439", reason="closed upstream"
    )
    assert st == "ok" and job is not None
    doc = gitclaim._load_queue_unlocked(home)
    assert doc["accepted"] == []
    assert not any(r.get("id") == "#4439" for r in (doc.get("unaccepted") or []))
    assert any(
        r.get("id") == "#4439"
        and str(r.get("result") or "").upper() == "CLOSED"
        for r in (doc.get("done") or [])
    )
    assert clear_calls == [(nick, "4439")]


def test_done_fr_after_closed_skips_mrb_needs_human(tmp_path: Path):
    home = _home(tmp_path)
    nick = "marchhare-18680"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                _fr_acc(
                    nick=nick,
                    state="closed",
                    cancel_pending=True,
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
        ident="#4439",
        result="",
        url="https://github.com/SimonBarnett/a-search/pull/4459",
    )
    assert st == "ok" and job is not None
    doc = gitclaim._load_queue_unlocked(home)
    assert doc["accepted"] == []
    assert not any(
        str(r.get("task") or "").upper() == "MRB" for r in (doc.get("unaccepted") or [])
    )
    done = [r for r in (doc.get("done") or []) if r.get("id") == "#4439"]
    assert done and done[0].get("needs_human") is True


def test_claim_from_payload_closed_carries_actor():
    payload = {
        "action": "closed",
        "sender": {"login": "SimonBarnett"},
        "repository": {"full_name": REPO},
        "issue": {
            "number": 4439,
            "title": "dup",
            "body": "Duplicate of #1343",
            "state": "closed",
            "labels": [],
        },
    }
    c = gitclaim.claim_from_payload("issues", payload)
    assert c is not None
    assert str(c.state or "").lower() == "closed"
    assert c.actor == "SimonBarnett"


def test_skill_pins_issue_open_before_pr_and_cancel():
    root = Path(__file__).resolve().parents[2]
    fr = (root / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    irc = (
        root / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "still open" in fr.lower() or "issue is still open" in fr.lower()
    assert "gh pr create" in fr.lower()
    assert "CANCEL" in irc
    assert "NACK" in irc
