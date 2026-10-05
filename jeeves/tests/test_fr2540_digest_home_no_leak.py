"""FR #2540: GET /bob/v1/report must not leak BOB_DIGEST_HOME into later queue_path."""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import bobcallback
import gitclaim
import jeeves_main
import registered_machines as rm


ALLOW = {"127.0.0.1"}


def test_github_pr_exists_checker_does_not_leak_bob_digest_home(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    other = tmp_path / "other"
    other.mkdir()
    gitclaim.github_pr_exists_checker(home=tmp_path, cache={})
    assert os.environ.get("BOB_DIGEST_HOME") in (None, "")
    assert gitclaim.queue_path(other) == other / gitclaim.QUEUE_NAME


def test_public_queue_get_report_does_not_redirect_later_queue(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    report_home = tmp_path / "report"
    offer_home = tmp_path / "offer"
    report_home.mkdir()
    offer_home.mkdir()
    rm.sync_from_chanserv(report_home, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])

    code, body = bobcallback.handle_request(
        "GET", "/bob/v1/report", {}, b"", "127.0.0.1", report_home, ALLOW
    )
    assert code == 200
    assert "marchhare" in json.loads(body)["roster_machine_ids"]
    assert os.environ.get("BOB_DIGEST_HOME") in (None, "")

    q = {
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "1993",
                "url": "https://github.com/SimonBarnett/bobiverse/issues/1993",
                "require_machine": "ionos",
            },
            {
                "repo": "SimonBarnett/other",
                "task": "FR",
                "id": "1",
                "url": "https://github.com/SimonBarnett/other/issues/1",
            },
        ],
        "accepted": {},
        "done": [],
    }
    (offer_home / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    (offer_home / "focus.json").write_text(
        json.dumps({"strict": True, "repos": {"SimonBarnett/bobiverse": {"priority": 1}}, "items": {}}),
        encoding="utf-8",
    )
    assert gitclaim.queue_path(offer_home) == offer_home / "queue.json"
    raw = json.loads((offer_home / "queue.json").read_text(encoding="utf-8"))
    assert len(raw.get("unaccepted") or []) == 2
    assert gitclaim.summarize_empty_offer(offer_home, "").get("unaccepted") == 2

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_self_test(
            home=offer_home,
            as_json=True,
            checks=["queue", "offer"],
            chair_home=offer_home,
        )
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    offer = payload.get("checks", {}).get("offer") or {}
    assert offer.get("unaccepted") == 2
    assert code in (0, 1, 2)
