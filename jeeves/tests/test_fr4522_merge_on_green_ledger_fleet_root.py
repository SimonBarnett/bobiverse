"""FR #4522: merge-on-green ledger lives beside queue.json (fleet root), not config home."""
from __future__ import annotations

import gitclaim
import mrb_merge_on_green

SHA = "c" * 40


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


def test_fr4522_pass_sha_reads_ledger_from_fleet_root_not_config_home(tmp_path, monkeypatch):
    """Chair --home is ~/.jeeves; ledger + queue live under BOB_DIGEST_HOME (~/.bobiverse)."""
    config_home = tmp_path / "jeeves-config"
    fleet_root = tmp_path / "bobiverse-fleet"
    config_home.mkdir()
    fleet_root.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(fleet_root))

    # Stamp as the seat/chair would: enqueue into the home the DONE path receives (config),
    # but the real live ledger is already under the fleet root (class of #4522).
    mrb_merge_on_green.enqueue(
        fleet_root,
        repo="o/a",
        pr="99",
        pass_sha=SHA,
        url="https://github.com/o/a/pull/99",
    )
    assert (fleet_root / "merge-on-green.json").is_file()
    assert not (config_home / "merge-on-green.json").is_file()

    # Empty config-home ledger must not hide the fleet ledger.
    assert gitclaim._merge_on_green_pass_sha(config_home, "o/a", 99) == SHA

    gitclaim._write_queue(
        gitclaim.queue_path(config_home),
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
                }
            ],
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
    res = gitclaim.resync_from_github(
        config_home,
        ["o/a"],
        fetch_json=_fetch(_pr(99, sha=SHA, auto_merge={"merge_method": "merge"})),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(config_home)
    assert [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"] == []


def test_fr4522_enqueue_writes_ledger_beside_queue(tmp_path, monkeypatch):
    config_home = tmp_path / "jeeves-config"
    fleet_root = tmp_path / "bobiverse-fleet"
    config_home.mkdir()
    fleet_root.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(fleet_root))

    mrb_merge_on_green.enqueue(
        config_home,
        repo="o/a",
        pr="42",
        pass_sha=SHA,
        url="https://github.com/o/a/pull/42",
    )
    assert (fleet_root / "merge-on-green.json").is_file()
    assert not (config_home / "merge-on-green.json").is_file()
    assert gitclaim._merge_on_green_pass_sha(config_home, "o/a", 42) == SHA
