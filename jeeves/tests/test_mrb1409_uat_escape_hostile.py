"""Hostile MRB #1409 / FR #2939: sole implementer after giveups stays self-UAT blocked.

#1409 originally required the escape hatch. FR #2939 removes escape (worker refuses
self-UAT) and escalates when every live seat is blocked.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/bobiverse"


def _digest(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "marchhare-41928", "state": "idle", "work": "", "updated": "2026-10-04T02:00:00Z"},
        ],
    }
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "workers": {},
        "worker_list": [
            {"nick": "win-mpre8vi4u6u-15656", "state": "idle", "work": "", "updated": "2026-10-04T02:00:00Z"},
        ],
    }
    bobreport.save_digest(home, doc)


def test_sole_active_implementer_after_giveup_stays_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path)
    uat = {
        "repo": REPO,
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "merged_prs": ["#1"],
        "refs": ["#1"],
        "giveup_seats": "marchhare-41928",
        "implementer_seat": "x",
    }
    for nick in ("marchhare-41928", "win-mpre8vi4u6u-15656"):
        gitclaim.ledger_touch(
            tmp_path, nick, REPO, "FR",
            ["simonbarnett/bobiverse#1", "simonbarnett/bobiverse#0"],
        )
    led = gitclaim.ledger_load(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    why = gitclaim.ledger_blocks(led, uat, "win-mpre8vi4u6u-15656", live)
    assert why and gitclaim.ledger_why_is_self_uat(why)
    assert gitclaim.row_gave_up_by(uat, "marchhare-41928")
    assert gitclaim.repo_uat_no_eligible_live_seat(led, uat, live)
    # Giveup seat still listed live but must not strand sibling via review_blocked
    # when the sibling is not the stamped author.
    assert not gitclaim.review_blocked_for_author(
        uat, "win-mpre8vi4u6u-15656", live, ledger=led
    )


def test_docs_uat_paragraph_has_no_control_chars():
    text = Path("jeeves/docs/jeeves-commands.md").read_text(encoding="utf-8")
    i = text.find("UAT is per REPO")
    assert i >= 0
    para = text[i : i + 1600]
    assert "repo_uat" in para
    assert "needs-human" in para
    assert "blocked" in para
    assert "release-gate" in para
    assert chr(8) not in para
    assert "self_uat" in para or "self-UAT" in para or "FR #2939" in para
    assert "fewer cycle FR touches" not in para
