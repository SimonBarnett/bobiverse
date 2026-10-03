"""FR #924: pull_request synchronize backfills author_seat on existing MRB rows."""
from __future__ import annotations

import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"


def test_synchronize_backfills_author_seat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare"})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#908",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{REPO}/pull/908",
                    "refs": ["#811"],
                }
            ],
            "accepted": [],
            "done": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#811",
                    "seq": 1,
                    "nick": "marchhare-41928",
                    "done_by": "marchhare-41928",
                    "ts": "t",
                    "line": "DONE FR",
                    "url": f"https://github.com/{REPO}/pull/908",
                }
            ],
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "synchronize",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 908,
                "title": "fix(bobiverse#811)",
                "body": f"Closes {REPO}#811",
                "html_url": f"https://github.com/{REPO}/pull/908",
            },
        },
    )
    assert claim is not None
    assert claim.action == "synchronize"
    assert claim.task == "MRB"
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#908"]
    assert len(mrbs) == 1
    assert mrbs[0].get("author_seat") == "marchhare-41928"
    assert mrbs[0].get("implementer_seat") == "marchhare-41928"
