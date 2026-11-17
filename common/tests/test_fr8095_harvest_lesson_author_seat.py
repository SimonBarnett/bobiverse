"""FR #8095: harvest-lesson MRB must stamp the filing seat and never self-offer."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines


NOW = 1_763_400_000.0
NICK = "flamingo-17852"
OTHER = "flamingo-11111"
REPO = "SimonBarnett/bobiverse"
PR_ID = "#8092"
PR_URL = f"https://github.com/{REPO}/pull/8092"
LESSON_BODY = (
    "MRB (light triage): is the lesson useful?\n\n"
    "Lessons:\n- tip\n\n"
    f"_source machine=`flamingo` agent=`Invoke-BobiverseHarvest` "
    f"book=`harvest` ver=`x` seat=`{NICK}`_\n"
)


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = {
        "v": 1,
        "machines": {
            "flamingo": {
                "id": "flamingo",
                "workers": {
                    "17852": {
                        "pid": "17852",
                        "nick": NICK,
                        "kind": "grok",
                        "state": "idle",
                        "start_model": "grok-4",
                    },
                    "11111": {
                        "pid": "11111",
                        "nick": OTHER,
                        "kind": "grok",
                        "state": "idle",
                        "start_model": "grok-4",
                    },
                },
                "worker_list": [
                    {"nick": NICK, "state": "idle", "kind": "grok"},
                    {"nick": OTHER, "state": "idle", "kind": "grok"},
                ],
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)
    return tmp_path


def test_fr8095_lesson_opener_prefers_seat_over_agent(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    assert gitclaim.lesson_pr_opener_seat(LESSON_BODY) == NICK
    # agent= alone that is not a seat nick must not invent an opener
    assert (
        gitclaim.lesson_pr_opener_seat(
            "_source agent=`Invoke-BobiverseHarvest` book=`harvest`_"
        )
        == ""
    )
    # Prefer seat= when both appear (agent is never a machine-pid seat)
    assert (
        gitclaim.lesson_pr_opener_seat(
            f"agent=`{OTHER}` seat=`{NICK}`"
        )
        == NICK
    )


def test_fr8095_labeled_backfill_stamps_filing_seat(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    opener = gitclaim.lesson_pr_opener_seat(LESSON_BODY)
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id=PR_ID,
        event="pull_request",
        action="labeled",
        line="",
        title="lesson(harvest): tip utf8 write playbook",
        body=LESSON_BODY,
        labels=["via-intake", "harvest-lesson"],
        state="open",
        harvest_lesson=True,
        opened_by=opener,
    )
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    assert gitclaim._apply_label_mutation(doc, claim, home=home) == "added"
    row = doc["unaccepted"][0]
    assert NICK in gitclaim.row_author_seats(row)
    assert gitclaim.review_blocked_for_author(row, NICK, {NICK, OTHER})
    assert not gitclaim.review_blocked_for_author(row, OTHER, {NICK, OTHER})


def test_fr8095_enrich_recovers_opener_from_body_when_stamp_missing(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": PR_ID,
        "url": PR_URL,
        "title": "lesson(harvest): tip",
        "labels": ["harvest-lesson"],
        "body": LESSON_BODY,
    }
    doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
    enriched = gitclaim.enrich_mrb_author_fields(doc, row)
    assert NICK in gitclaim.row_author_seats(enriched)


def test_fr8095_offer_focus_blocks_filing_seat(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": PR_ID,
                    "seq": 1,
                    "url": PR_URL,
                    "title": "lesson(harvest): tip",
                    "labels": ["harvest-lesson", "via-intake"],
                    "body": LESSON_BODY,
                    "author_seat": NICK,
                    "implementer_seat": NICK,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status != "ok" or job is None or str(job.get("id")) != PR_ID

    status2, job2 = gitclaim.offer_focus_top(home, OTHER, "#flamingo", now=NOW)
    assert status2 == "ok"
    assert job2 is not None
    assert str(job2.get("id")) == PR_ID
