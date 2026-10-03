"""FR #785: never offer/enqueue archived repos; rewrite gh-Jeeves -> bobiverse."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import chair_health as ch  # noqa: E402
import gitclaim  # noqa: E402


GHJ = "SimonBarnett/gh-Jeeves"
BOB = "SimonBarnett/bobiverse"


def _seed(home: Path, rows: list[dict]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {"unaccepted": rows, "accepted": [], "done": []}
    (home / "queue.json").write_text(json.dumps(doc), encoding="utf-8")


def test_canonical_queue_repo_rewrites_gh_jeeves():
    assert gitclaim.canonical_queue_repo(GHJ) == BOB
    assert gitclaim.canonical_queue_repo("simonbarnett/gh-jeeves") == BOB
    assert gitclaim.canonical_queue_repo(BOB) == BOB
    assert gitclaim.repo_archived_for_queue(GHJ) is True
    assert gitclaim.repo_archived_for_queue(BOB) is False


def test_claim_from_payload_skips_archived_open_events():
    payload = {
        "action": "opened",
        "repository": {"full_name": GHJ, "archived": True},
        "issue": {"number": 239, "title": "x", "body": "", "state": "open", "labels": []},
    }
    assert gitclaim.claim_from_payload("issues", payload) is None

    # Known archived map without payload.archived flag still skips enqueue.
    payload2 = {
        "action": "opened",
        "repository": {"full_name": GHJ, "archived": False},
        "issue": {"number": 239, "title": "x", "body": "", "state": "open", "labels": []},
    }
    assert gitclaim.claim_from_payload("issues", payload2) is None


def test_claim_from_payload_closed_on_archived_still_builds_claim():
    """Closed events must still flow so prune can drop stale queue rows."""
    payload = {
        "action": "closed",
        "repository": {"full_name": GHJ, "archived": True},
        "issue": {"number": 239, "title": "x", "body": "", "state": "closed", "labels": []},
    }
    claim = gitclaim.claim_from_payload("issues", payload)
    assert claim is not None
    assert claim.repo == GHJ
    assert claim.action == "closed"


def test_offer_focus_top_skips_archived_repo_rows(tmp_path):
    _seed(
        tmp_path,
        [
            {
                "repo": GHJ,
                "task": "FR",
                "id": "#239",
                "title": "archived bait",
                "url": f"https://github.com/{GHJ}/issues/239",
                "seq": 1,
            },
            {
                "repo": BOB,
                "task": "FR",
                "id": "#785",
                "title": "live work",
                "url": f"https://github.com/{BOB}/issues/785",
                "seq": 2,
            },
        ],
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job["repo"] == BOB
    assert job["id"] == "#785"


def test_prune_drops_archived_repo_rows(tmp_path):
    _seed(
        tmp_path,
        [
            {"repo": GHJ, "task": "FR", "id": "#239", "title": "gone", "seq": 1},
            {"repo": BOB, "task": "FR", "id": "#785", "title": "keep", "seq": 2},
        ],
    )
    out = gitclaim.prune_unassignable_queue(tmp_path)
    assert out["ok"] is True
    assert out["dropped"] >= 1
    doc = gitclaim.load_queue(tmp_path)
    repos = {r["repo"] for r in doc["unaccepted"]}
    assert GHJ not in repos
    assert BOB in repos


def test_discover_rewrites_gh_jeeves_config_to_bobiverse(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    (tmp_path / "resync-repos.txt").write_text(f"{GHJ}\n{BOB}\n", encoding="utf-8")
    getter = lambda url: []  # noqa: E731
    got = ch.discover_repos(tmp_path, {"simonbarnett"}, getter, ignored=[])
    assert BOB in got
    assert GHJ not in got
    # rewrite must not duplicate bobiverse
    assert got.count(BOB) == 1


def test_discover_queue_rows_rewrite_archived_source(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    _seed(
        tmp_path,
        [{"repo": GHJ, "task": "FR", "id": "#1", "title": "stale", "seq": 1}],
    )
    getter = lambda url: []  # noqa: E731
    got = ch.discover_repos(tmp_path, {"simonbarnett"}, getter, ignored=[])
    assert BOB in got
    assert GHJ not in got
