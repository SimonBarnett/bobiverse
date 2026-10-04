"""fr_done must not suppress FRs that GitHub still wants (open issue, no open Closes PR)."""
from __future__ import annotations

from pathlib import Path

import gitclaim


def test_resync_enqueues_open_fr_despite_fr_done(tmp_path, monkeypatch):
    """Regression: #1201 stayed open with fr_done and vanished from the offer queue."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}', encoding="utf-8"
    )

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})["simonbarnett/bobiverse#1201"] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _stamp)

    issues = [
        {
            "number": 1201,
            "title": "bob-worker deletes outbox.txt after drain",
            "body": "fix: recreate outbox",
            "state": "open",
            "labels": [{"name": "via-intake"}],
        }
    ]
    prs: list = []

    def fake_fetch(url: str):
        if "/pulls" in url:
            return prs
        if "/issues" in url:
            return issues
        return []

    monkeypatch.setattr(gitclaim, "repo_archived_for_queue", lambda *a, **k: False)

    summary = gitclaim.resync_from_github(
        home, ["SimonBarnett/bobiverse"], fetch_json=fake_fetch, token="x"
    )
    assert summary.get("ok") is True
    doc = gitclaim.load_queue(home)
    ids = [(r.get("task"), r.get("id")) for r in doc.get("unaccepted") or []]
    assert ("FR", "#1201") in ids
    led = gitclaim.ledger_load(home)
    assert "simonbarnett/bobiverse#1201" not in (led.get("fr_done") or {})
    # Every seat must be able to take it again (not "PR pending merge").
    assert gitclaim.ledger_blocks(led, {"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#1201"}, "win-mpre8vi4u6u-1", None) == ""
