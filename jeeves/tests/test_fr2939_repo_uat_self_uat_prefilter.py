"""FR #2939: repo UAT pre-offer self-UAT (FR+MRB), empty-reply self_uat, all-blocked escalate.

Regression of #1416: Jeeves offered UAT #0 to seats that only MRB'd the cycle; they
ACK then GIVEUP self-UAT; after every live seat gave up the row stayed ledger-blocked
with no escape that a worker would accept.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim


REPO = "SimonBarnett/bobiverse"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest(home: Path) -> None:
    _roster(home)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "marchhare-28308", "state": "idle", "work": "", "updated": "2026-10-06T20:00:00Z"},
            {"nick": "marchhare-40412", "state": "idle", "work": "", "updated": "2026-10-06T20:00:00Z"},
        ],
    }
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "win-mpre8vi4u6u-15656", "state": "idle", "work": "", "updated": "2026-10-06T20:00:00Z"},
        ],
    }
    bobreport.save_digest(home, doc)


def _uat_row(**extra):
    row = {
        "repo": REPO,
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "title": "UAT SimonBarnett/bobiverse",
        "merged_prs": ["#2906", "#2912", "#2936"],
        "refs": ["#2906", "#2912", "#2936"],
        "implementer_seat": "marchhare-28308",
        "author_seat": "marchhare-28308",
    }
    row.update(extra)
    return row


def test_mrb_only_seat_is_self_uat_blocked(tmp_path, monkeypatch):
    """MRB ACK/DONE stamps role MRB — must block repo UAT like the worker skill."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-40412",
        REPO,
        "MRB",
        ["simonbarnett/bobiverse#2936", "simonbarnett/bobiverse#0"],
    )
    led = gitclaim.ledger_load(tmp_path)
    why = gitclaim._ledger_blocks(led, uat, "marchhare-40412")
    assert why and gitclaim.ledger_why_is_self_uat(why)
    assert gitclaim.ledger_blocks(led, uat, "marchhare-40412", gitclaim.live_seat_nicks(tmp_path))


def test_fr_author_still_self_uat_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-28308",
        REPO,
        "FR",
        ["simonbarnett/bobiverse#2906", "simonbarnett/bobiverse#0"],
    )
    led = gitclaim.ledger_load(tmp_path)
    why = gitclaim.ledger_blocks(led, uat, "marchhare-28308", gitclaim.live_seat_nicks(tmp_path))
    assert why and gitclaim.ledger_why_is_self_uat(why)


def test_fresh_seat_not_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-28308",
        REPO,
        "FR",
        ["simonbarnett/bobiverse#2906", "simonbarnett/bobiverse#0"],
    )
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-40412",
        REPO,
        "MRB",
        ["simonbarnett/bobiverse#2936", "simonbarnett/bobiverse#0"],
    )
    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live) == ""
    assert not gitclaim.repo_uat_no_eligible_live_seat(led, uat, live)


def test_no_escape_when_all_self_uat(tmp_path, monkeypatch):
    """FR #2939: all-blocked must NOT lift a self-UAT seat (old #1407 escape)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()
    for nick, role, pr in (
        ("marchhare-28308", "FR", "#2906"),
        ("marchhare-40412", "MRB", "#2936"),
        ("win-mpre8vi4u6u-15656", "FR", "#2912"),
    ):
        gitclaim.ledger_touch(
            tmp_path,
            nick,
            REPO,
            role,
            [f"simonbarnett/bobiverse{pr}", "simonbarnett/bobiverse#0"],
        )
    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.repo_uat_no_eligible_live_seat(led, uat, live)
    for nick in live:
        why = gitclaim.ledger_blocks(led, uat, nick, live)
        assert why and gitclaim.ledger_why_is_self_uat(why)


def test_escalate_stamps_needs_human_and_announces(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [uat], "accepted": [], "done": []},
    )
    for nick, role, pr in (
        ("marchhare-28308", "FR", "#2906"),
        ("marchhare-40412", "MRB", "#2936"),
        ("win-mpre8vi4u6u-15656", "FR", "#2912"),
    ):
        gitclaim.ledger_touch(
            tmp_path,
            nick,
            REPO,
            role,
            [f"simonbarnett/bobiverse{pr}", "simonbarnett/bobiverse#0"],
        )
    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.maybe_escalate_repo_uat_all_self_uat(
        tmp_path, uat, live=live, ledger=led
    )
    doc = gitclaim._load_queue_unlocked(tmp_path)
    row = doc["unaccepted"][0]
    assert row.get("needs_human") is True
    assert row.get("self_uat_escalated") is True
    outbox = bobreport.fleet_digest_home(tmp_path) / "chair-outbox.txt"
    text = outbox.read_text(encoding="utf-8")
    assert "self-UAT" in text
    assert "fresh" in text.lower() or "uninvolved" in text.lower()
    # Second call must not re-announce.
    size = outbox.stat().st_size
    assert gitclaim.maybe_escalate_repo_uat_all_self_uat(
        tmp_path, row, live=live, ledger=led
    )
    assert outbox.stat().st_size == size


def test_summarize_empty_offer_reports_self_uat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row(author_seat="marchhare-28308", implementer_seat="marchhare-28308")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [uat], "accepted": [], "done": []},
    )
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-28308",
        REPO,
        "FR",
        ["simonbarnett/bobiverse#2906", "simonbarnett/bobiverse#0"],
    )
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-40412",
        REPO,
        "MRB",
        ["simonbarnett/bobiverse#2936", "simonbarnett/bobiverse#0"],
    )
    stats = gitclaim.summarize_empty_offer(tmp_path, "marchhare-40412")
    assert int(stats.get("self_uat") or 0) >= 1
    detail = gitclaim.format_empty_offer_detail("marchhare-40412", stats)
    assert "self_uat=" in detail


def test_exact_author_stays_blocked_even_when_others_gave_up(tmp_path, monkeypatch):
    """FR #2939 supersedes #1416 exact-author escape — escalate instead of offer."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()
    for nick in ("marchhare-40412", "win-mpre8vi4u6u-15656"):
        gitclaim.ledger_giveup(tmp_path, nick, REPO, "UAT", "#0")
    gitclaim.ledger_touch(
        tmp_path,
        "marchhare-28308",
        REPO,
        "FR",
        ["simonbarnett/bobiverse#2906", "simonbarnett/bobiverse#0"],
    )
    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    enriched = dict(uat)
    enriched["author_seat"] = "marchhare-28308"
    enriched["implementer_seat"] = "marchhare-28308"
    assert gitclaim.review_blocked_for_author(
        enriched, "marchhare-28308", live, ledger=led
    )
    assert gitclaim.ledger_blocks(led, uat, "marchhare-28308", live)
