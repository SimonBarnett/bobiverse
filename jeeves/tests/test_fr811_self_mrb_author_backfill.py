"""FR #811 / #831: backfill author_seat on existing MRB so self-MRB is never offered."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"


def test_pr_edited_backfills_author_seat_on_existing_mrb(tmp_path, monkeypatch):
    """Webhook race: MRB row exists without author_seat; later event stamps implementer."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#790",
                "seq": 1,
                "ts": "t",
                "line": "x",
                "url": f"https://github.com/{REPO}/pull/790",
                "refs": ["#781"],
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#781",
                "seq": 1,
                "nick": "marchhare-41928",
                "done_by": "marchhare-41928",
                "ts": "t",
                "line": "DONE FR",
                "url": f"https://github.com/{REPO}/pull/790",
            }
        ],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "edited",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 790,
                "title": "fix(fr-781)",
                "body": f"Closes {REPO}#781",
                "html_url": f"https://github.com/{REPO}/pull/790",
            },
        },
    )
    assert claim is not None
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB" and r.get("id") == "#790"]
    assert len(mrbs) == 1
    assert mrbs[0].get("author_seat") == "marchhare-41928"
    assert mrbs[0].get("implementer_seat") == "marchhare-41928"


def test_offer_skips_implementer_after_author_backfill(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"41928": {"state": "idle"}}
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(home, digest)

    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#790",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "title": "fix(fr-781)",
                    "url": f"https://github.com/{REPO}/pull/790",
                    "refs": ["#781"],
                    "author_seat": "marchhare-41928",
                    "implementer_seat": "marchhare-41928",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    monkeypatch.setattr(
        gitclaim,
        "ordered_unaccepted",
        lambda h, rows: sorted(rows, key=gitclaim._sort_key),
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    # Only row is self-MRB → empty (skipped), not offered to implementer.
    assert st == "empty"
    assert job is None
