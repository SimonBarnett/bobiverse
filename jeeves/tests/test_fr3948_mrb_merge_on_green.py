"""FR #3948: merge-on-green handoff — pass-then-green, red/SHA requeue, hold skip."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")
mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")


PASS_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _pass_board(sha: str = PASS_SHA) -> list[dict]:
    return [
        {
            "user": {"login": "flamingo-1"},
            "author_association": "NONE",
            "body": (
                f"## MRB board — PASS\n\n**Verdict:** PASS\n"
                f"MRB PASS @ {sha}\nmerge-on-green pending sha={sha}"
            ),
            "created_at": "2026-10-11T10:00:00Z",
        }
    ]


def test_decide_pass_then_green_merges():
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=PASS_SHA,
            checks="success",
        )
        == "merge"
    )
    # No reported checks still merges when SHA matches (repos without required checks).
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=PASS_SHA,
            checks="none",
        )
        == "merge"
    )


def test_decide_pass_then_red_requeues():
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=PASS_SHA,
            checks="failure",
        )
        == "requeue_ci"
    )


def test_decide_sha_change_requeues():
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=OTHER_SHA,
            checks="success",
        )
        == "requeue_sha"
    )


def test_decide_hold_skips_even_when_green():
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=PASS_SHA,
            checks="success",
            hold_reason="hold label: on-hold",
        )
        == "skip_hold"
    )


def test_decide_pending_checks_wait():
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=PASS_SHA,
            current_sha=PASS_SHA,
            checks="pending",
        )
        == "wait"
    )


def test_parse_pass_sha_from_comment():
    text = f"MRB PASS @ {PASS_SHA[:12]}\nmerge-on-green pending"
    assert mrb_merge_on_green.parse_pass_sha_from_text(text) == PASS_SHA[:12]
    assert (
        mrb_merge_on_green.parse_pass_sha_from_comments(_pass_board()) == PASS_SHA
    )


def test_process_pass_then_green_calls_merge(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="1406",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/1406",
    )
    merges: list[tuple[str, str, str]] = []

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "labels": [],
            "title": "fix",
            "body": "Closes #1",
            "checks": "success",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda r, p: _pass_board(),
        merge_fn=lambda r, p, sha: merges.append((r, p, sha)) or {"merged": True},
    )
    assert summary["merged"] == 1
    assert merges == [("SimonBarnett/a-search", "1406", PASS_SHA)]
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []


def test_process_pass_then_red_requeues(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="1434",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/1434",
    )
    gitclaim.stamp_mrb_done(home, "SimonBarnett/a-search", "#1434")

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "labels": [],
            "title": "fix",
            "body": "",
            "checks": "failure",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda r, p: _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
    )
    assert summary["requeued"] == 1
    assert summary["merged"] == 0
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []
    assert not gitclaim.mrb_ledger_done_hold(home, "SimonBarnett/a-search", "#1434")
    q = gitclaim.load_queue(home)
    assert any(
        str(r.get("task")).upper() == "MRB" and str(r.get("id")).lstrip("#") == "1434"
        for r in (q.get("unaccepted") or [])
    )


def test_process_sha_change_requeues(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/bobiverse",
        pr="3930",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/bobiverse/pull/3930",
    )

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": OTHER_SHA,
            "merged": False,
            "labels": [],
            "title": "new push",
            "body": "",
            "checks": "success",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda r, p: _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
    )
    assert summary["requeued"] == 1
    assert summary["merged"] == 0


def test_process_hold_never_merges(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="1334",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/1334",
    )
    merges: list = []

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "labels": ["on-hold"],
            "title": "held",
            "body": "On hold: must not merge until #1358.",
            "checks": "success",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda r, p: _pass_board()
        + [
            {
                "user": {"login": "SimonBarnett"},
                "author_association": "OWNER",
                "body": "On hold: must not merge until #1358.",
                "created_at": "2026-10-11T11:00:00Z",
            }
        ],
        merge_fn=lambda r, p, sha: merges.append((r, p, sha)),
    )
    assert summary["skipped_hold"] == 1
    assert summary["merged"] == 0
    assert merges == []
    pending = mrb_merge_on_green.load_ledger(home)["pending"]
    assert len(pending) == 1
    assert pending[0]["status"] == "skip_hold"


def test_enqueue_from_done_pass_only(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert (
        mrb_merge_on_green.enqueue_from_done(
            home,
            repo="SimonBarnett/a-search",
            pr_url="https://github.com/SimonBarnett/a-search/pull/1406",
            result="FAIL",
            fetch_pr=lambda *_a, **_k: {"sha": PASS_SHA, "labels": [], "title": "", "body": ""},
        )
        is None
    )
    row = mrb_merge_on_green.enqueue_from_done(
        home,
        repo="SimonBarnett/a-search",
        pr_url="https://github.com/SimonBarnett/a-search/pull/1406",
        result="PASS",
        nick="flamingo-11336",
        fetch_pr=lambda *_a, **_k: {
            "sha": PASS_SHA,
            "labels": [],
            "title": "ok",
            "body": "",
            "html_url": "https://github.com/SimonBarnett/a-search/pull/1406",
        },
    )
    assert row is not None
    assert row["pass_sha"] == PASS_SHA
    assert row["pr"] == "1406"


def test_job_mrb_skill_documents_fr3948_no_ci_poll():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #3948" in text
    assert "merge-on-green" in text or "merge on green" in text.lower()
    # Seats must not be told to watch CI to completion.
    assert "gh pr checks --watch" not in text or "Never" in text
    assert "never poll" in text.lower() or "Never poll" in text
    agents = ROOT / "bob" / "agents" / "worker" / "AGENTS.md"
    agents_txt = agents.read_text(encoding="utf-8")
    assert "3948" in agents_txt
