"""Lesson PRs that cite an FR must not make that FR's implementer their author.

2026-10-06: audit lesson PRs #2718-#2725 (opened by the operator) said ``Refs #2705``.
The PR-opened webhook took ``refs`` -> ``fr_implementer_seat_from_doc`` and stamped
``implementer_seat=marchhare-39556`` (FR #2705 implementer). That seat was then
self-MRB blocked from all eight, and the ledger ``touch`` on #2705 blocked it again
via the row's refs. A lesson PR's author is whoever opened it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import bobreport
import gitclaim


REPO = "SimonBarnett/bobiverse"
FR_SEAT = "marchhare-39556"
OPENER_SEAT = "marchhare-20452"


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


def _queue(home: Path, *, unaccepted=(), accepted=(), done=()):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(unaccepted), "accepted": list(accepted), "done": list(done)},
    )


def _done_fr(num=2705, nick=FR_SEAT):
    return {"repo": REPO, "task": "FR", "id": f"#{num}", "nick": nick, "done_by": nick, "ts": "t", "line": "x"}


def _pr_payload(num, *, title, body, labels=(), action="opened"):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": num,
            "title": title,
            "body": body,
            "draft": False,
            "state": "open",
            "labels": [{"name": x} for x in labels],
        },
    }


LESSON_BODY = (
    "MRB: verify that the lesson is generalised and placed in the right SKILL.md, then merge.\n\n"
    "Lessons:\n- Keep GitHub calls outside the queue lock.\n\n"
    "Refs #2705 (audit for FR #2705)\n"
)


def _mrb_row(home: Path, num: int) -> dict:
    doc = gitclaim._load_queue_unlocked(home)
    for r in doc.get("unaccepted") or []:
        if r.get("task") == "MRB" and gitclaim._norm_row_id(r.get("id")) == f"#{num}":
            return r
    raise AssertionError(f"no MRB row #{num}: {doc.get('unaccepted')}")


def test_lesson_pr_citing_fr_has_no_fr_implementer_author(tmp_path):
    _queue(tmp_path, done=[_done_fr()])
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(2718, title="lesson(bobiverse-bob-job-fr): harvest digest", body=LESSON_BODY, labels=["harvest-lesson"]),
    )
    assert claim is not None
    gitclaim.apply_queue_event(tmp_path, claim)
    row = _mrb_row(tmp_path, 2718)
    assert FR_SEAT not in gitclaim.row_author_seats(row)
    assert not row.get("refs"), "lesson PR refs must not link it to the cited FR"


def test_lesson_pr_does_not_supersede_cited_open_fr(tmp_path):
    fr = {"repo": REPO, "task": "FR", "id": "#2729", "ts": "t", "line": "x", "seq": 1}
    _queue(tmp_path, unaccepted=[fr])
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(2740, title="lesson(harvest): note", body="Lessons:\n- x\n\nCloses #2729\n", labels=["via-intake", "harvest-lesson"]),
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    doc = gitclaim._load_queue_unlocked(tmp_path)
    assert any(r.get("task") == "FR" and r.get("id") == "#2729" for r in doc["unaccepted"])


def test_lesson_pr_author_is_opener_seat_from_intake_footer(tmp_path):
    _queue(tmp_path, done=[_done_fr()])
    body = LESSON_BODY + (
        "\n---\n_via-intake id=`in_x` ts=`t`_\n"
        f"_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`harvest` ver=`-` seat=`{OPENER_SEAT}`_\n"
    )
    claim = gitclaim.claim_from_payload(
        "pull_request", _pr_payload(2719, title="lesson(harvest): x", body=body, labels=["via-intake", "harvest-lesson"])
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    assert gitclaim.row_author_seats(_mrb_row(tmp_path, 2719)) == [OPENER_SEAT]


def test_stale_lesson_row_is_healed_on_ready_for_review(tmp_path):
    stale = {
        "repo": REPO, "task": "MRB", "id": "#2720", "ts": "t", "line": "x", "seq": 1,
        "url": f"https://github.com/{REPO}/pull/2720", "refs": ["#2705"],
        "author_seat": FR_SEAT, "implementer_seat": FR_SEAT,
    }
    _queue(tmp_path, unaccepted=[stale], done=[_done_fr()])
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(2720, title="lesson(bobiverse-bob-job-uat): digest", body=LESSON_BODY, labels=["harvest-lesson"], action="ready_for_review"),
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    row = _mrb_row(tmp_path, 2720)
    assert gitclaim.row_author_seats(row) == []
    assert not row.get("refs")


def test_fr_implementer_not_ledger_blocked_from_lesson_mrb(tmp_path):
    _queue(tmp_path, done=[_done_fr()])
    claim = gitclaim.claim_from_payload(
        "pull_request", _pr_payload(2721, title="lesson(x): y", body=LESSON_BODY, labels=["harvest-lesson"])
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    row = _mrb_row(tmp_path, 2721)
    ledger = {"v": 1, "touch": {gitclaim._lkey(REPO, "#2705"): {FR_SEAT.lower(): ["FR"]}}, "giveup": {}}
    assert gitclaim._ledger_blocks(ledger, row, FR_SEAT) == ""


def test_resync_lesson_pr_has_no_refs(tmp_path):
    _queue(tmp_path, done=[_done_fr()])

    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return [{"number": 2722, "title": "lesson(harvest): digest", "body": LESSON_BODY,
                     "labels": [{"name": "harvest-lesson"}], "draft": False}]
        if "/issues?" in url or ("/pulls?" in url and "state=closed" in url):
            return []
        raise AssertionError(url)

    gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch)
    row = _mrb_row(tmp_path, 2722)
    assert not row.get("refs")
    assert FR_SEAT not in gitclaim.row_author_seats(row)


def test_non_lesson_pr_still_gets_fr_implementer(tmp_path):
    """Regression guard: a real implement PR (Closes #N) keeps FR #593 attribution."""
    _queue(tmp_path, done=[_done_fr()])
    claim = gitclaim.claim_from_payload(
        "pull_request", _pr_payload(2723, title="FR #2705: harvest lessons", body="Closes #2705\n")
    )
    gitclaim.apply_queue_event(tmp_path, claim)
    assert FR_SEAT in gitclaim.row_author_seats(_mrb_row(tmp_path, 2723))


def test_intake_footer_carries_seat():
    import intake

    norm = {"source": {"machine": "marchhare", "agent": "Invoke-BobiverseHarvest", "skill_book": "harvest", "seat": OPENER_SEAT}}
    foot = intake._provenance_footer(norm, "in_x", quarantine=False)
    assert f"seat=`{OPENER_SEAT}`" in foot
    assert gitclaim.lesson_pr_opener_seat(foot) == OPENER_SEAT
