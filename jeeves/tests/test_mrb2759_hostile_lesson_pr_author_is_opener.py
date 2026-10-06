"""MRB #2759 hostile: lesson PR author is opener, never cited FR implementer."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import intake
import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "jeeves" / "tests" / "test_lesson_pr_author_is_opener.py"
HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"

REPO = "SimonBarnett/bobiverse"
FR_SEAT = "marchhare-39556"
OPENER = "marchhare-20452"


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        bobreport,
        "parse_seat_nick",
        lambda n: (str(n).rsplit("-", 1)[0], str(n).rsplit("-", 1)[1])
        if str(n or "").lower().startswith("marchhare-") and str(n).rsplit("-", 1)[1].isdigit()
        else None,
    )
    yield


def test_mrb2759_product_suite_present():
    text = PRODUCT.read_text(encoding="utf-8")
    assert "test_lesson_pr_citing_fr_has_no_fr_implementer_author" in text
    assert "test_non_lesson_pr_still_gets_fr_implementer" in text
    assert "test_closed_unmerged_pr_does_not_requeue_itself_as_fr" in text


def test_mrb2759_is_harvest_lesson_pr_helpers():
    assert gitclaim.is_harvest_lesson_pr(title="lesson(harvest): x", labels=())
    assert gitclaim.is_harvest_lesson_pr(title="FR #1: x", labels=("harvest-lesson",))
    assert not gitclaim.is_harvest_lesson_pr(title="FR #2705: harvest lessons", labels=())


def test_mrb2759_lesson_opener_seat_from_footer():
    foot = (
        f"_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` "
        f"book=`harvest` ver=`-` seat=`{OPENER}`_"
    )
    assert gitclaim.lesson_pr_opener_seat(foot) == OPENER
    assert gitclaim.lesson_pr_opener_seat("agent=`Invoke-BobiverseHarvest`") == ""


def test_mrb2759_claim_lesson_has_no_refs_and_opener():
    body = (
        "Refs #2705\n---\n"
        f"_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`x` ver=`-` seat=`{OPENER}`_\n"
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 2718,
                "title": "lesson(bobiverse-bob-job-fr): digest",
                "body": body,
                "draft": False,
                "labels": [{"name": "harvest-lesson"}],
            },
        },
    )
    assert claim is not None
    assert claim.harvest_lesson is True
    assert claim.refs == ()
    assert claim.opened_by == OPENER


def test_mrb2759_apply_does_not_stamp_fr_implementer(tmp_path):
    home = tmp_path
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#2705",
                    "nick": FR_SEAT,
                    "done_by": FR_SEAT,
                    "ts": "t",
                    "line": "x",
                }
            ],
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 2888,
                "title": "lesson(harvest): note",
                "body": "Refs #2705\n",
                "draft": False,
                "labels": [{"name": "harvest-lesson"}],
            },
        },
    )
    gitclaim.apply_queue_event(home, claim)
    doc = gitclaim._load_queue_unlocked(home)
    row = next(r for r in doc["unaccepted"] if r.get("id") == "#2888")
    assert FR_SEAT not in gitclaim.row_author_seats(row)
    assert not row.get("refs")


def test_mrb2759_harvest_ps1_sends_source_seat():
    """FR #2790: prefer BOB_NICK (bob-worker) then BOB_AGENT_NICK (legacy)."""
    text = HARVEST_PS1.read_text(encoding="utf-8")
    assert "BOB_NICK" in text
    assert "BOB_AGENT_NICK" in text
    assert "seat =" in text or "seat=" in text.replace(" ", "")
    # Prefer worker seat nick over the legacy Watch-AgentHealth name.
    nick_idx = text.index("BOB_NICK")
    agent_idx = text.index("BOB_AGENT_NICK", nick_idx + 1)
    assert nick_idx < agent_idx


def test_mrb2759_intake_footer_seat_roundtrip():
    norm = {
        "source": {
            "machine": "marchhare",
            "agent": "Invoke-BobiverseHarvest",
            "skill_book": "harvest",
            "seat": OPENER,
        }
    }
    foot = intake._provenance_footer(norm, "in_x", quarantine=False)
    assert f"seat=`{OPENER}`" in foot
