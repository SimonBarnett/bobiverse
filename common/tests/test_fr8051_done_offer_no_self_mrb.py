"""FR #8051: done-offer must never hand an MRB to the FR implementer seat."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen


NOW = 1_763_300_000.0
NICK = "flamingo-17916"
REPO = "SimonBarnett/bobiverse"
FR_ID = "#7999"
PR_ID = "#8044"
PR_URL = f"https://github.com/{REPO}/pull/8044"


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
                    "17916": {
                        "pid": "17916",
                        "nick": NICK,
                        "kind": "grok",
                        "state": "idle",
                        "start_model": "grok-4",
                    }
                },
                "worker_list": [{"nick": NICK, "state": "idle", "kind": "grok"}],
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)
    return tmp_path


def _accepted_fr(home: Path) -> None:
    fr = {
        "repo": REPO,
        "task": "FR",
        "id": FR_ID,
        "seq": 1,
        "url": f"https://github.com/{REPO}/issues/7999",
        "nick": NICK,
        "accepted_ts": "2026-11-17T15:00:00Z",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [fr], "done": []},
    )


def test_fr8051_done_offer_does_not_self_mrb_even_when_only_idle_seat(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _accepted_fr(home)
    status, _ = shop_listen.complete_job_by_ref(
        home,
        nick=NICK,
        repo=REPO,
        task="FR",
        ident=FR_ID,
        result="PR",
        url=PR_URL,
    )
    assert status == "ok"
    q = json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))
    mrb = next(r for r in q["unaccepted"] if str(r.get("task")).upper() == "MRB")
    assert NICK in gitclaim.row_author_seats(mrb)

    offers: list[str] = []

    def say(_ch: str, text: str) -> bool:
        offers.append(text)
        return True

    n, job = gitclaim.offer_after_done(home, NICK, "#flamingo", say=say, now=NOW)
    assert n == 0 and job is None
    assert offers == []
    assert not any(PR_ID in line for line in offers)


def test_fr8051_done_offer_blocks_when_author_stamp_missing(tmp_path, monkeypatch):
    """Race: stamp stripped after DONE; done-offer must still refuse self-MRB."""
    home = _home(tmp_path, monkeypatch)
    _accepted_fr(home)
    shop_listen.complete_job_by_ref(
        home,
        nick=NICK,
        repo=REPO,
        task="FR",
        ident=FR_ID,
        result="PR",
        url=PR_URL,
    )
    q = json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))
    for row in q.get("unaccepted") or []:
        if str(row.get("task") or "").upper() != "MRB":
            continue
        row.pop("author_seat", None)
        row.pop("implementer_seat", None)
        row.pop("author_nick", None)
        row.pop("author", None)
        row.pop("author_seats", None)
    gitclaim._write_queue(gitclaim.queue_path(home), q)
    assert gitclaim.row_author_seats(q["unaccepted"][0]) == []

    offers: list[str] = []

    def say(_ch: str, text: str) -> bool:
        offers.append(text)
        return True

    n, job = gitclaim.offer_after_done(home, NICK, "#flamingo", say=say, now=NOW)
    assert n == 0 and job is None
    assert offers == []


def test_fr8051_enrich_recovers_implementer_from_done_fr(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _accepted_fr(home)
    shop_listen.complete_job_by_ref(
        home,
        nick=NICK,
        repo=REPO,
        task="FR",
        ident=FR_ID,
        result="PR",
        url=PR_URL,
    )
    q = json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))
    for row in q.get("unaccepted") or []:
        row.pop("author_seat", None)
        row.pop("implementer_seat", None)
    gitclaim._write_queue(gitclaim.queue_path(home), q)
    doc = gitclaim.load_queue(home)
    mrb = next(r for r in doc["unaccepted"] if str(r.get("task")).upper() == "MRB")
    enriched = gitclaim.enrich_mrb_author_fields(doc, mrb)
    assert NICK in gitclaim.row_author_seats(enriched)
    assert gitclaim.review_blocked_for_author(enriched, NICK, {NICK})
