"""Hostile MRB #1480 / FR #2389: open Closes-PR keeps MRB; clears fr_done; FR not re-queued while superseded."""
from __future__ import annotations

import gitclaim


def test_resync_still_skips_fr_superseded_by_open_pr_despite_fr_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})["simonbarnett/bobiverse#99"] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _stamp)

    issues = [
        {
            "number": 99,
            "title": "FR: still open until PR merges",
            "body": "work",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        }
    ]
    prs = [
        {
            "number": 100,
            "title": "Implement FR #99",
            "body": "Closes SimonBarnett/bobiverse#99\n",
            "state": "open",
            "html_url": "https://github.com/SimonBarnett/bobiverse/pull/100",
            "head": {"ref": "fr-99"},
            "base": {"ref": "main"},
            "user": {"login": "dev"},
        }
    ]

    def fake_fetch(url: str):
        if "/pulls" in url:
            return prs
        if "/issues" in url:
            # GitHub issues API includes PRs; keep FR-shaped only for simplicity
            return issues
        return []

    monkeypatch.setattr(gitclaim, "repo_archived_for_queue", lambda *a, **k: False)
    summary = gitclaim.resync_from_github(
        home, ["SimonBarnett/bobiverse"], fetch_json=fake_fetch, token="x"
    )
    assert summary.get("ok") is True
    doc = gitclaim.load_queue(home)
    ids = [(r.get("task"), r.get("id")) for r in doc.get("unaccepted") or []]
    # FR #2389: MRB must be present; FR not re-queued while MRB supersedes.
    assert ("MRB", "#100") in ids
    assert ("FR", "#99") not in ids
    # Stamp must clear so seats are not told "already delivered" for 24h with no merged closer.
    led = gitclaim.ledger_load(home)
    assert "simonbarnett/bobiverse#99" not in (led.get("fr_done") or {})
