"""FR #4466: resync must not re-queue an open PR waiting on CI after MRB PASS."""
from __future__ import annotations

import gitclaim
import mrb_merge_on_green

SHA = "a" * 40
OTHER = "b" * 40


def _pr(n: int, *, sha: str, auto_merge: dict | None):
    return {
        "number": n,
        "title": "fix: x",
        "body": "Closes o/a#50",
        "html_url": f"https://github.com/o/a/pull/{n}",
        "state": "open",
        "draft": False,
        "auto_merge": auto_merge,
        "head": {"sha": sha},
        "user": {"login": "u"},
    }


def _fetch(pr):
    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    return fetch_json


def _seed(tmp_path, *, queued: bool):
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "MRB",
                    "id": "#99",
                    "seq": 1,
                    "ts": "t",
                    "line": "",
                    "url": "https://github.com/o/a/pull/99",
                    "offered_to": "marchhare-1",
                }
            ]
            if queued
            else [],
            "accepted": [],
            "done": [
                {
                    "repo": "o/a",
                    "task": "MRB",
                    "id": "#99",
                    "result": "PASS",
                    "url": "https://github.com/o/a/pull/99",
                }
            ],
        },
    )


def test_open_pr_waiting_on_ci_requires_auto_merge_and_sha():
    pr = _pr(99, sha=SHA, auto_merge={"merge_method": "merge"})
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, SHA) is True
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, OTHER) is False
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, "") is False
    off = _pr(99, sha=SHA, auto_merge=None)
    assert gitclaim.open_pr_mrb_waiting_on_ci(off, SHA) is False


def test_resync_prunes_automerged_pass_same_sha(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path, queued=True)
    mrb_merge_on_green.enqueue(
        tmp_path, repo="o/a", pr="99", pass_sha=SHA, url="https://github.com/o/a/pull/99"
    )
    res = gitclaim.resync_from_github(
        tmp_path,
        ["o/a"],
        fetch_json=_fetch(_pr(99, sha=SHA, auto_merge={"merge_method": "merge"})),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"] == []
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(r.get("task") == "MRB" and r.get("id") == "#99" for r in done)


def test_resync_requeues_when_head_sha_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path, queued=False)
    mrb_merge_on_green.enqueue(
        tmp_path, repo="o/a", pr="99", pass_sha=SHA, url="https://github.com/o/a/pull/99"
    )
    gitclaim.resync_from_github(
        tmp_path,
        ["o/a"],
        fetch_json=_fetch(_pr(99, sha=OTHER, auto_merge={"merge_method": "merge"})),
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    mrb = [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"]
    assert len(mrb) == 1


def test_resync_requeues_when_auto_merge_off(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path, queued=False)
    mrb_merge_on_green.enqueue(
        tmp_path, repo="o/a", pr="99", pass_sha=SHA, url="https://github.com/o/a/pull/99"
    )
    gitclaim.resync_from_github(
        tmp_path,
        ["o/a"],
        fetch_json=_fetch(_pr(99, sha=SHA, auto_merge=None)),
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    mrb = [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"]
    assert len(mrb) == 1


def test_resync_skips_when_ledger_in_fleet_root_not_config_home(tmp_path, monkeypatch):
    """Live chair: resync gets ~/.jeeves, ledger + queue live in BOB_DIGEST_HOME (~/.bobiverse)."""
    cfg = tmp_path / "cfg"
    fleet = tmp_path / "fleet"
    cfg.mkdir()
    fleet.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(fleet))
    _seed(cfg, queued=True)
    mrb_merge_on_green.enqueue(
        fleet, repo="o/a", pr="99", pass_sha=SHA, url="https://github.com/o/a/pull/99"
    )
    assert not (cfg / mrb_merge_on_green.LEDGER_NAME).exists()
    res = gitclaim.resync_from_github(
        cfg,
        ["o/a"],
        fetch_json=_fetch(_pr(99, sha=SHA, auto_merge={"merge_method": "merge"})),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(cfg)
    assert [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"] == []
