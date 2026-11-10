"""FR #6434: detect CodeRabbit ready/skipped reliably; flag-off stays full."""
from __future__ import annotations

import fuel_chain
import gitclaim


def test_fr6434_fixture_bot_review_stamps_ready_one_poll(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    sha = "bd8900cce860b8061221ba79442d8d826e3a064e"
    reviews = [
        {
            "user": {"login": "coderabbitai[bot]"},
            "commit_id": sha,
            "state": "COMMENTED",
            "body": "<!-- coderabbit-ai-generated:v1 -->\n\n**Actionable comments posted: 0**\n",
        }
    ]

    def lookup(repo, num):
        return fuel_chain.coderabbit_state_from_surfaces(
            reviews=reviews, checks=[], comments=[], head_sha=sha
        )

    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#6432",
        "head_sha": sha,
        "coderabbit_wait_since": 10.0,
        "coderabbit_head_sha": sha,
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 20.0, lookup=lookup)
    assert hold is False
    assert row.get("coderabbit") == "ready"
    assert row.get("review") == "light"
    assert "ready" in str(row.get("coderabbit_reason") or "")


def test_fr6434_short_head_sha_matches_full_commit_id(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    full = "bd8900cce860b8061221ba79442d8d826e3a064e"
    reviews = [{"user": {"login": "coderabbitai[bot]"}, "commit_id": full, "body": "ok"}]

    def lookup(repo, num):
        return fuel_chain.coderabbit_state_from_surfaces(
            reviews=reviews, checks=[], comments=[], head_sha="bd8900cc"
        )

    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#1",
        "head_sha": "bd8900cc",
        "coderabbit_wait_since": 1.0,
        "coderabbit_head_sha": "bd8900cc",
    }
    assert fuel_chain.apply_mrb_coderabbit_gate(row, 2.0, lookup=lookup) is False
    assert row["coderabbit"] == "ready"


def test_fr6434_check_run_covers_ready(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    sha = "deadbeef01"
    checks = [
        {"name": "CodeRabbit", "head_sha": sha, "status": "completed", "conclusion": "success"}
    ]

    def lookup(repo, num):
        return fuel_chain.coderabbit_state_from_surfaces(
            reviews=[], checks=checks, comments=[], head_sha=sha
        )

    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#2",
        "head_sha": sha,
        "coderabbit_wait_since": 1.0,
        "coderabbit_head_sha": sha,
    }
    assert fuel_chain.apply_mrb_coderabbit_gate(row, 2.0, lookup=lookup) is False
    assert row["coderabbit"] == "ready"


def test_fr6434_skipped_walkthrough_stamps_skipped_no_wait(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    comments = [
        {
            "user": {"login": "coderabbitai[bot]"},
            "body": (
                "<!-- This is an auto-generated comment: skip review by coderabbit.ai -->\n"
                "> [!IMPORTANT]\n> ## Review skipped\n>\n> Ignore keyword(s) in the title.\n"
            ),
        }
    ]

    def lookup(repo, num):
        return fuel_chain.coderabbit_state_from_surfaces(
            reviews=[], checks=[], comments=comments, head_sha="abc"
        )

    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#6431",
        "head_sha": "abc",
        "coderabbit_wait_since": 1000.0,
        "coderabbit_head_sha": "abc",
    }
    # Immediately after enqueue — must not hold for the 12 min window.
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 1001.0, lookup=lookup)
    assert hold is False
    assert str(row.get("coderabbit") or "").startswith("skipped")
    assert "ignore-keyword" in str(row.get("coderabbit") or "") or "ignore-keyword" in str(
        row.get("coderabbit_reason") or ""
    )
    assert row.get("review") == "full"
    line = gitclaim.format_assign_line("n-1", row)
    assert "coderabbit=skipped" in line
    assert "review=full" in line


def test_fr6434_skipped_pr_closed_and_non_default_base():
    closed = [
        {
            "user": {"login": "coderabbitai[bot]"},
            "body": "## Review skipped\n\nPR is closed.\n",
        }
    ]
    st = fuel_chain.coderabbit_state_from_surfaces(
        reviews=[], checks=[], comments=closed, head_sha="x"
    )
    assert st["skipped"] is True
    assert st["skip_why"] == "pr-closed"

    base = [
        {
            "user": {"login": "coderabbitai[bot]"},
            "body": "## Review skipped\n\nNon-default base branch.\n",
        }
    ]
    st2 = fuel_chain.coderabbit_state_from_surfaces(
        reviews=[], checks=[], comments=base, head_sha="x"
    )
    assert st2["skipped"] is True
    assert st2["skip_why"] == "non-default-base"


def test_fr6434_no_review_times_out(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)

    def lookup(repo, num):
        return {"ready": False, "failed": False, "skipped": False, "activity": True, "skip_why": ""}

    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#9",
        "head_sha": "t9",
        "coderabbit_wait_since": 100.0,
        "coderabbit_head_sha": "t9",
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 100.0 + 12 * 60 + 1, lookup=lookup)
    assert hold is False
    assert row.get("coderabbit") == "timeout"
    assert row.get("review") == "full"


def test_fr6434_flag_off_stamps_off_full(monkeypatch):
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    row = {"task": "MRB", "repo": "o/r", "id": "#1", "url": "https://github.com/o/r/pull/1"}
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 10.0)
    assert hold is False
    assert row.get("coderabbit") == "off"
    assert row.get("review") == "full"


def test_fr6434_webhook_review_stamps_queue_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    home = tmp_path / "chair"
    home.mkdir()
    sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#7001",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/7001",
                    "title": "pr",
                    "line": "MRB #7001",
                    "seq": 1,
                    "state": "open",
                    "head_sha": sha,
                    "coderabbit": "pending",
                    "coderabbit_wait_since": 1.0,
                    "coderabbit_head_sha": sha,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    payload = {
        "action": "submitted",
        "review": {
            "user": {"login": "coderabbitai[bot]"},
            "commit_id": sha,
            "state": "commented",
            "body": "<!-- coderabbit-ai-generated:v1 -->\n\n**Actionable comments posted: 0**\n",
        },
        "pull_request": {
            "number": 7001,
            "html_url": "https://github.com/SimonBarnett/bobiverse/pull/7001",
            "head": {"sha": sha},
            "base": {"ref": "main"},
        },
        "repository": {"full_name": "SimonBarnett/bobiverse"},
    }
    out = gitclaim.stamp_coderabbit_from_webhook(home, "pull_request_review", payload)
    assert out.get("stamped") == "ready"
    doc = gitclaim._load_queue_unlocked(home)
    row = doc["unaccepted"][0]
    assert row["coderabbit"] == "ready"
    assert row["review"] == "light"


def test_fr6434_webhook_skip_comment_stamps_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#7002",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/7002",
                    "title": "lesson(harvest): x",
                    "line": "MRB #7002",
                    "seq": 2,
                    "state": "open",
                    "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "coderabbit": "pending",
                    "coderabbit_wait_since": 1.0,
                    "coderabbit_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    payload = {
        "action": "created",
        "comment": {
            "user": {"login": "coderabbitai[bot]"},
            "body": (
                "<!-- skip review by coderabbit.ai -->\n"
                "## Review skipped\nIgnore keyword(s) in the title.\n"
            ),
        },
        "issue": {
            "number": 7002,
            "html_url": "https://github.com/SimonBarnett/bobiverse/pull/7002",
            "pull_request": {"url": "https://api.github.com/repos/SimonBarnett/bobiverse/pulls/7002"},
        },
        "repository": {"full_name": "SimonBarnett/bobiverse"},
    }
    out = gitclaim.stamp_coderabbit_from_webhook(home, "issue_comment", payload)
    assert str(out.get("stamped") or "").startswith("skipped")
    doc = gitclaim._load_queue_unlocked(home)
    assert str(doc["unaccepted"][0]["coderabbit"]).startswith("skipped")
