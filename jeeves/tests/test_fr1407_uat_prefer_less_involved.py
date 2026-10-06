"""FR #1407 / FR #2939: repo UAT self-UAT prefilter (no refuse-then-escape).

Historically #1407 preferred the less-involved seat when every live seat had FR
touches (escape hatch). FR #2939 aligns the chair with the worker self-UAT skill:
FR *or* MRB cycle touch blocks offer, and all-blocked escalates instead of lifting
a seat that will GIVEUP.
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


def _digest_two_machines(home: Path) -> None:
    _roster(home)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "marchhare-41928", "state": "idle", "work": "", "updated": "2026-10-04T02:00:00Z"},
            {"nick": "marchhare-35600", "state": "idle", "work": "", "updated": "2026-10-04T02:00:00Z"},
        ],
    }
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "win-mpre8vi4u6u-15656", "state": "idle", "work": "", "updated": "2026-10-04T02:00:00Z"},
            {"nick": "win-mpre8vi4u6u-20596", "state": "idle", "work": "", "updated": "2026-10-04T02:00:00Z"},
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
        "line": "UAT SimonBarnett/bobiverse: all issues closed",
        "merged_prs": ["#1393", "#1384", "#1328", "#1143", "#1010"],
        "refs": ["#1393", "#1384", "#1328", "#1143", "#1010"],
        "implementer_seat": "win-mpre8vi4u6u-20596",
        "mrb_author_seat": "win-mpre8vi4u6u-20596",
        "author_seat": "win-mpre8vi4u6u-20596",
    }
    row.update(extra)
    return row


def test_all_fr_touched_seats_stay_blocked_no_escape(tmp_path, monkeypatch):
    """FR #2939: former #1407 escape must not lift any self-UAT seat."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_two_machines(tmp_path)
    uat = _uat_row()

    for nick, prs in (
        ("marchhare-41928", ("#1393", "#1384", "#1328")),
        ("marchhare-35600", ("#1393", "#1384")),
        ("win-mpre8vi4u6u-15656", ("#1143",)),
        ("win-mpre8vi4u6u-20596", ("#1010",)),
    ):
        for pr in prs:
            gitclaim.ledger_touch(
                tmp_path, nick, REPO, "FR",
                [f"simonbarnett/bobiverse{pr}", "simonbarnett/bobiverse#0"],
            )

    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.repo_uat_no_eligible_live_seat(led, uat, live)
    for nick in ("marchhare-41928", "win-mpre8vi4u6u-15656"):
        why = gitclaim.ledger_blocks(led, uat, nick, live)
        assert why and gitclaim.ledger_why_is_self_uat(why)


def test_sibling_ignores_giveup_and_implementer_others(tmp_path, monkeypatch):
    """Sibling without cycle FR/MRB touches may take UAT when others gave up / are blocked."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_two_machines(tmp_path)
    uat = _uat_row(giveup_seats="marchhare-41928,marchhare-35600")

    for nick, prs in (
        ("marchhare-41928", ("#1393", "#1384", "#1328")),
        ("marchhare-35600", ("#1393", "#1384")),
        ("win-mpre8vi4u6u-20596", ("#1010",)),
    ):
        for pr in prs:
            gitclaim.ledger_touch(
                tmp_path, nick, REPO, "FR",
                [f"simonbarnett/bobiverse{pr}", "simonbarnett/bobiverse#0"],
            )
    # 15656 has no FR/MRB touch — eligible fresh seat on author machine.

    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)

    assert gitclaim.review_blocked_for_author(uat, "win-mpre8vi4u6u-20596", live, ledger=led)
    assert not gitclaim.review_blocked_for_author(
        uat, "win-mpre8vi4u6u-15656", live, ledger=led
    )
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live) == ""
    assert gitclaim.row_gave_up_by(uat, "marchhare-41928")


def test_equal_fr_counts_stay_blocked(tmp_path, monkeypatch):
    """FR #2939: equal involvement still self-UAT — escalate, do not escape."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_two_machines(tmp_path)
    uat = _uat_row()
    for nick in ("marchhare-41928", "marchhare-35600", "win-mpre8vi4u6u-15656", "win-mpre8vi4u6u-20596"):
        gitclaim.ledger_touch(
            tmp_path, nick, REPO, "FR",
            ["simonbarnett/bobiverse#1393", "simonbarnett/bobiverse#0"],
        )
    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.ledger_blocks(led, uat, "marchhare-41928", live)
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live)
    assert gitclaim.repo_uat_no_eligible_live_seat(led, uat, live)
