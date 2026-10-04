"""FR #1416: UAT must not strand when live seats are ledger-giveup + one implementer.

Also: needs-mrb1 issues must not hold the repo UAT gate (circular strand when the
monitor files a needs-mrb1 FR about stranded UAT).
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
            {"nick": "marchhare-41928", "state": "idle", "work": "", "updated": "2026-10-04T03:00:00Z"},
            {"nick": "marchhare-35600", "state": "idle", "work": "", "updated": "2026-10-04T03:00:00Z"},
        ],
    }
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "win-mpre8vi4u6u-15656", "state": "idle", "work": "", "updated": "2026-10-04T03:00:00Z"},
            {"nick": "win-mpre8vi4u6u-20596", "state": "idle", "work": "", "updated": "2026-10-04T03:00:00Z"},
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
        "merged_prs": ["#1393", "#1010"],
        "refs": ["#1393", "#1010"],
        "implementer_seat": "win-mpre8vi4u6u-20596",
        "author_seat": "win-mpre8vi4u6u-20596",
    }
    row.update(extra)
    return row


def test_needs_mrb1_does_not_block_repo_uat_gate():
    assert gitclaim.issue_blocks_repo_uat(
        title="UAT stranded",
        labels=["feature-request", "via-intake", "needs-mrb1"],
        state="open",
    ) is False
    assert gitclaim.issue_blocks_repo_uat(
        title="FR: real work",
        labels=["feature-request"],
        state="open",
    ) is True
    assert gitclaim.issue_blocks_repo_uat(
        title="harvest: x",
        labels=["skill", "via-intake"],
        state="open",
    ) is False


def test_ledger_giveup_seats_excluded_from_escape_pool(tmp_path, monkeypatch):
    """After resync, giveup_seats is empty but ledger still has GIVEUPs.

    Giveup seats have 0 FR touches and must not steal the less-involved pick
    from the sole implementer who should escape.
    """
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = _uat_row()  # no giveup_seats — mimics fresh resync row

    # Three seats GIVEUP'd UAT (durable ledger only).
    for nick in ("marchhare-41928", "marchhare-35600", "win-mpre8vi4u6u-15656"):
        gitclaim.ledger_giveup(tmp_path, nick, REPO, "UAT", "#0")

    # Sole remaining seat is the implementer.
    gitclaim.ledger_touch(
        tmp_path, "win-mpre8vi4u6u-20596", REPO, "FR",
        ["simonbarnett/bobiverse#1010", "simonbarnett/bobiverse#0"],
    )

    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)

    assert "gave up" in gitclaim._ledger_blocks(led, uat, "marchhare-41928")
    assert "implemented" in gitclaim._ledger_blocks(led, uat, "win-mpre8vi4u6u-20596")

    # Escape must lift the implementer even though giveup seats are "live".
    assert gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-20596", live) == ""
    # Giveup seats stay blocked (escape only lifts "implemented").
    assert gitclaim.ledger_blocks(led, uat, "marchhare-41928", live)
