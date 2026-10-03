"""FR #1080 / PR #1122: needs-mrb1 must not become require_machine=mrb1; per-seat cooldown; focus fallback."""
from __future__ import annotations

import bobreport
import focus_ignore
import gitclaim
import registered_machines


def test_needs_mrb1_label_does_not_infer_machine():
    assert gitclaim.infer_require_machine(title="x", body="y", labels=("needs-mrb1",)) == ""
    assert gitclaim.infer_require_machine(title="x", body="y", labels=("needs-human",)) == ""
    # Real machine cue still works.
    assert gitclaim.infer_require_machine(title="x", body="y", labels=("needs-ionos",)) == "ionos"


def test_corrupt_mrb1_stamp_ignored():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#1",
        "require_machine": "mrb1",
        "labels": ["needs-mrb1", "feature-request"],
    }
    assert gitclaim.row_require_machine(row) == ""
    assert gitclaim.row_skip_fr_reason(row)


def test_needs_mrb1_not_enqueued(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "issue": {
                "number": 1080,
                "title": "FR: needs-mrb1 must not become require_machine=mrb1",
                "body": "fix skip",
                "state": "open",
                "labels": [
                    {"name": "feature-request"},
                    {"name": "needs-mrb1"},
                    {"name": "via-intake"},
                ],
            },
        },
    )
    assert claim is None


def test_row_on_cooldown_per_seat():
    now = 1_700_000_000.0
    row = {
        "cooldown_until": "2099-01-01T00:00:00Z",
        "giveup_seats": "marchhare-1",
    }
    assert gitclaim.row_on_cooldown(row, now, "marchhare-1") is True
    assert gitclaim.row_on_cooldown(row, now, "marchhare-2") is False
    assert gitclaim.row_on_cooldown(row, now, "") is True


def test_offer_focus_fallback_when_strict_hides_rows(tmp_path, monkeypatch):
    """When focus order yields nothing eligible, fall back to full unaccepted."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos"})
    digest = bobreport.empty_digest()
    for mid in ("marchhare", "ionos"):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {"1": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    # Strict focus only bobiverse; offerable row is Club-Madeira (out of focus).
    focus_ignore.save_focus(
        tmp_path,
        {
            "v": 1,
            "repos": {
                "SimonBarnett/bobiverse": {
                    "priority": 1,
                    "label": "bobiverse",
                    "ts": "t",
                }
            },
            "items": {},
            "item_seq": 0,
            "strict": True,
        },
    )
    assert focus_ignore.is_strict(tmp_path) is True
    assert (
        focus_ignore.sort_unaccepted_rows(
            tmp_path,
            [
                {
                    "repo": "SimonBarnett/Club-Madeira",
                    "task": "FR",
                    "id": "#2",
                    "seq": 1,
                }
            ],
        )
        == []
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/Club-Madeira",
                    "task": "FR",
                    "id": "#2",
                    "seq": 1,
                    "ts": "t",
                    "line": "email campaign",
                    "title": "FR: email campaign",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert job["repo"] == "SimonBarnett/Club-Madeira"
    assert job["id"] == "#2"