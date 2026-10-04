"""FR #1407: repo UAT must not strand on self-UAT GIVEUP loops.

When every live seat implemented something (escape hatch), prefer the seat with
fewer cycle FR touches. Sibling review_blocked must ignore giveup seats and
other-machine seats that are themselves implementer-blocked.
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


def test_escape_prefers_fewer_fr_touches(tmp_path, monkeypatch):
    """Heavy MRB-fix author stays blocked while a lighter implementer may escape."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_two_machines(tmp_path)
    uat = _uat_row()

    # Heavy author (marchhare-41928): three recent MRB-fix PRs.
    for pr in ("#1393", "#1384", "#1328"):
        gitclaim.ledger_touch(
            tmp_path, "marchhare-41928", REPO, "FR",
            [f"simonbarnett/bobiverse{pr}", "simonbarnett/bobiverse#0"],
        )
    # Lighter author (ionos-15656): one older PR only.
    gitclaim.ledger_touch(
        tmp_path, "win-mpre8vi4u6u-15656", REPO, "FR",
        ["simonbarnett/bobiverse#1143", "simonbarnett/bobiverse#0"],
    )
    # Exact stamped author also implemented.
    gitclaim.ledger_touch(
        tmp_path, "win-mpre8vi4u6u-20596", REPO, "FR",
        ["simonbarnett/bobiverse#1010", "simonbarnett/bobiverse#0"],
    )
    # 35600 also heavy so escape still considers "all active blocked".
    for pr in ("#1393", "#1384"):
        gitclaim.ledger_touch(
            tmp_path, "marchhare-35600", REPO, "FR",
            [f"simonbarnett/bobiverse{pr}", "simonbarnett/bobiverse#0"],
        )

    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)

    assert gitclaim._ledger_blocks(led, uat, "marchhare-41928")
    assert gitclaim._ledger_blocks(led, uat, "win-mpre8vi4u6u-15656")

    # Prefer less-involved: 15656 may escape; 41928 stays blocked.
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live) == ""
    why_heavy = gitclaim.ledger_blocks(led, uat, "marchhare-41928", live)
    assert why_heavy and "self-UAT" in why_heavy


def test_sibling_ignores_giveup_and_implementer_others(tmp_path, monkeypatch):
    """After marchhare self-UAT GIVEUP, ionos sibling of author stamp may take UAT."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_two_machines(tmp_path)
    uat = _uat_row(giveup_seats="marchhare-41928,marchhare-35600")

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

    # Exact author still blocked.
    assert gitclaim.review_blocked_for_author(uat, "win-mpre8vi4u6u-20596", live, ledger=led)

    # Sibling used to stay blocked while giveup marchhare seats remained "live".
    assert not gitclaim.review_blocked_for_author(
        uat, "win-mpre8vi4u6u-15656", live, ledger=led
    )

    # And ledger lets the lighter ionos seat through.
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live) == ""
    assert gitclaim.row_gave_up_by(uat, "marchhare-41928")


def test_equal_fr_counts_still_escape_both(tmp_path, monkeypatch):
    """Equal involvement → classic escape hatch (anyone may)."""
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
    assert gitclaim.ledger_blocks(led, uat, "marchhare-41928", live) == ""
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live) == ""
