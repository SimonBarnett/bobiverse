"""FR #4522: merge-on-green ledger lives beside queue.json (fleet root), not config home."""
from __future__ import annotations

import pytest

import gitclaim
import mrb_merge_on_green

SHA = "c" * 40


def _homes(tmp_path, monkeypatch, *, suite_mode: bool):
    """Chair config_home + fleet digest root.

    Setting BOB_HOME=config_home marks jeeves-config as the chair so
    bobreport.fleet_digest_home still redirects to BOB_DIGEST_HOME under
    BOBIVERSE_BUILD_SUITE (FR #6523 / FR #69). Non-chair tmp homes stay local
    (covered by test_fr6523_isolated_suite_digest_home).
    """
    config_home = tmp_path / "jeeves-config"
    fleet_root = tmp_path / "bobiverse-fleet"
    config_home.mkdir()
    fleet_root.mkdir()
    monkeypatch.setenv("BOB_HOME", str(config_home))
    monkeypatch.setenv("BOB_DIGEST_HOME", str(fleet_root))
    if suite_mode:
        monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    else:
        monkeypatch.delenv("BOBIVERSE_BUILD_SUITE", raising=False)
    return config_home, fleet_root


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
        # Keep resync offline: skip fetch_pr_state / detail / files lookups.
        "checks": "pending",
        "mergeable": True,
        "mergeable_state": "clean",
        "files": [{"filename": "x.py"}],
    }


def _fetch(pr):
    """URL-specific fetcher (class of FR #4683). Record unexpected URLs."""
    other: list[str] = []

    def fetch_json(url: str, force_refresh: bool = False):
        del force_refresh
        if "/search/repositories" in url:
            return {"items": []}
        if "/issues?" in url and "state=open" in url:
            return []
        if "/pulls?" in url and "state=open" in url:
            return [pr]
        if "/pulls?" in url and "state=closed" in url:
            return []
        other.append(url)
        return []

    fetch_json.other = other  # type: ignore[attr-defined]
    return fetch_json


@pytest.mark.parametrize("suite_mode", [True, False], ids=["suite-on", "suite-off"])
def test_fr4522_pass_sha_reads_ledger_from_fleet_root_not_config_home(
    tmp_path, monkeypatch, suite_mode
):
    """Chair --home is ~/.jeeves; ledger + queue live under BOB_DIGEST_HOME (~/.bobiverse)."""
    config_home, fleet_root = _homes(tmp_path, monkeypatch, suite_mode=suite_mode)

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
    fetch_hits: list[tuple] = []

    def spy_fetch_pr_state(*a, **k):
        fetch_hits.append((a, k))
        raise AssertionError("fetch_pr_state must not be called when checks is set")

    monkeypatch.setattr(mrb_merge_on_green, "fetch_pr_state", spy_fetch_pr_state)
    fetcher = _fetch(_pr(99, sha=SHA, auto_merge={"merge_method": "merge"}))
    res = gitclaim.resync_from_github(
        config_home,
        ["o/a"],
        fetch_json=fetcher,
    )
    assert res.get("ok") is True
    assert fetch_hits == [], "fetch_pr_state must stay unused when pr['checks'] is set"
    assert fetcher.other == [], f"unexpected GitHub URLs: {fetcher.other}"
    rows = gitclaim.load_unaccepted(config_home)
    assert [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"] == []


@pytest.mark.parametrize("suite_mode", [True, False], ids=["suite-on", "suite-off"])
def test_fr4522_enqueue_writes_ledger_beside_queue(tmp_path, monkeypatch, suite_mode):
    config_home, fleet_root = _homes(tmp_path, monkeypatch, suite_mode=suite_mode)

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
    assert gitclaim.queue_path(config_home) == fleet_root / "queue.json"
