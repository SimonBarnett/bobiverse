"""Hostile MRB #1480: fr_done clear must not re-offer FRs superseded by an open Closes PR."""
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
    assert ("FR", "#99") not in ids
