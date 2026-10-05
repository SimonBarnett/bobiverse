"""FR #2389: open Closes-PR must not eject open issue from desired or stick fr_done."""
from __future__ import annotations

import gitclaim


def test_resync_clears_fr_done_with_open_closes_pr_and_keeps_mrb(tmp_path, monkeypatch):
    """Open issue + open Closes PR + fr_done → fr_done cleared; MRB present; FR not re-offered while MRB supersedes."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})["simonbarnett/bobiverse#2380"] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _stamp)

    issues = [
        {
            "number": 2380,
            "title": "bob-worker: seat goes IRC-silent after compaction",
            "body": "fix outbox",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        }
    ]
    prs = [
        {
            "number": 2382,
            "title": "fix(fr-2380): BOB_OUTBOX env",
            "body": "Closes SimonBarnett/bobiverse#2380\n",
            "state": "open",
            "html_url": "https://github.com/SimonBarnett/bobiverse/pull/2382",
            "head": {"ref": "fr/2380-bob-outbox-env"},
            "base": {"ref": "main"},
            "user": {"login": "bob"},
        }
    ]

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
    assert ("MRB", "#2382") in ids
    # FR stays out of unaccepted while MRB supersedes (offer path), but fr_done must clear.
    assert ("FR", "#2380") not in ids
    led = gitclaim.ledger_load(home)
    assert "simonbarnett/bobiverse#2380" not in (led.get("fr_done") or {})
    # ledger_blocks must not claim "already delivered" once stamp is gone.
    assert (
        gitclaim.ledger_blocks(
            led,
            {"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#2380"},
            "marchhare-40208",
            None,
        )
        == ""
    )


def test_resync_requeues_fr_when_open_closes_pr_missing(tmp_path, monkeypatch):
    """If the Closes PR vanished but the issue is still open, FR must return after fr_done."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})["simonbarnett/bobiverse#2383"] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _stamp)

    issues = [
        {
            "number": 2383,
            "title": "bob-worker: no-ACK recycle",
            "body": "remind",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        }
    ]

    def fake_fetch(url: str):
        if "/pulls" in url:
            return []
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
    assert ("FR", "#2383") in ids
    led = gitclaim.ledger_load(home)
    assert "simonbarnett/bobiverse#2383" not in (led.get("fr_done") or {})
