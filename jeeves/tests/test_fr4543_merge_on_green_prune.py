"""FR #4543: prune closed/merged ledger rows; skip closed holds; back off when rate budget is low."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")

PASS_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _pass_board(sha: str = PASS_SHA) -> list[dict]:
    return [
        {
            "user": {"login": "flamingo-1"},
            "author_association": "NONE",
            "body": f"## MRB board\n**Verdict:** PASS\nMRB PASS @ {sha}",
            "created_at": "2026-10-17T03:00:00Z",
        }
    ]


def test_decide_closed_unmerged_drops():
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=PASS_SHA,
            checks="success",
            closed=True,
        )
        == "drop_closed"
    )


def test_process_drops_closed_without_fetching_comments(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/bobiverse",
        pr="4109",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/bobiverse/pull/4109",
    )
    comment_calls: list[tuple[str, str]] = []

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "closed": True,
            "labels": [],
            "title": "MRB CLOSED - not-useful",
            "body": "Do not merge",
            "checks": "none",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda r, p: comment_calls.append((r, p)) or _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
    )
    assert summary["dropped"] == 1
    assert comment_calls == []
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []


def test_process_drops_closed_hold_without_keeping(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="1563",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/1563",
        hold_reason="MRB CLOSED",
    )

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "closed": True,
            "labels": ["on-hold"],
            "title": "held closed",
            "body": "On hold",
            "checks": "success",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("closed PR must not fetch comments")
        ),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
    )
    assert summary["dropped"] == 1
    assert summary["skipped_hold"] == 0
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []


def test_process_backs_off_when_rate_remaining_low(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="3632",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/3632",
    )
    fetches: list[str] = []

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda r, p: fetches.append(f"{r}#{p}")
        or {
            "sha": PASS_SHA,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "x",
            "body": "",
            "checks": "success",
            "html_url": "",
        },
        fetch_comments=lambda *_a, **_k: _pass_board(),
        merge_fn=lambda *_a, **_k: {"merged": True},
        rate_remaining=lambda: 40,
        min_rate_remaining=100,
    )
    assert summary.get("backed_off") is True
    assert fetches == []
    assert summary["seen"] == 1
    assert len(mrb_merge_on_green.load_ledger(home)["pending"]) == 1


def test_process_open_green_still_merges_when_budget_ok(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="3632",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/3632",
    )
    merges: list = []
    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda r, p: {
            "repo": r,
            "pr": p,
            "sha": PASS_SHA,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "ok",
            "body": "",
            "checks": "success",
            "html_url": f"https://github.com/{r}/pull/{p}",
        },
        fetch_comments=lambda *_a, **_k: _pass_board(),
        merge_fn=lambda r, p, sha: merges.append((r, p, sha)) or {"merged": True},
        rate_remaining=lambda: 500,
        min_rate_remaining=100,
    )
    assert summary.get("backed_off") is not True
    assert summary["merged"] == 1
    assert merges == [("SimonBarnett/a-search", "3632", PASS_SHA)]
