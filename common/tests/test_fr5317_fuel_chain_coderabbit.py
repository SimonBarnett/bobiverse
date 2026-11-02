"""FR #5317: CodeRabbit-first fuel chain is off by default and never load-bearing."""
from __future__ import annotations

import gitclaim
import fuel_chain
import shop_listen


def test_fuel_stages_off_by_default(monkeypatch):
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    monkeypatch.delenv("BOB_FUEL_COPILOT", raising=False)
    monkeypatch.delenv("BOB_FUEL_FLEET", raising=False)
    assert fuel_chain.stage_enabled("coderabbit") is False
    assert fuel_chain.stage_enabled("copilot") is False
    assert fuel_chain.stage_enabled("fleet") is False
    assert fuel_chain.active_stages() == ()


def test_coderabbit_review_detects_bot_on_head_sha():
    sha = "abc123def456"
    reviews = [
        {"user": {"login": "coderabbitai[bot]"}, "commit_id": sha + "00"},
    ]
    assert fuel_chain.coderabbit_reviewed_head(reviews, [], sha) is True
    assert fuel_chain.coderabbit_reviewed_head([], [], sha) is False
    assert fuel_chain.coderabbit_reviewed_head(reviews, [], "ffff") is False


def test_coderabbit_review_detects_check_name():
    sha = "deadbeef"
    checks = [
        {
            "name": "CodeRabbit",
            "head_sha": sha,
            "status": "completed",
            "conclusion": "neutral",
        }
    ]
    assert fuel_chain.coderabbit_reviewed_head([], checks, sha) is True
    assert fuel_chain.coderabbit_reviewed_head([], [{"name": "ci", "head_sha": sha, "status": "completed"}], sha) is False


def test_mrb_hold_skipped_when_stage_off():
    row = {"task": "MRB", "repo": "o/r", "id": "#1", "url": "https://github.com/o/r/pull/1"}
    hold, tag = fuel_chain.mrb_coderabbit_offer(
        row,
        now=1000.0,
        enabled=False,
        has_review=False,
        wait_s=900,
    )
    assert hold is False
    assert tag == "off"


def test_mrb_hold_until_review_or_timeout():
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#9",
        "url": "https://github.com/o/r/pull/9",
    }
    hold, tag = fuel_chain.mrb_coderabbit_offer(
        row,
        now=100.0,
        enabled=True,
        has_review=False,
        wait_s=900,
        first_seen=100.0,
        activity=True,
    )
    assert hold is True
    assert tag == "pending"

    hold_r, tag_r = fuel_chain.mrb_coderabbit_offer(
        row,
        now=200.0,
        enabled=True,
        has_review=True,
        wait_s=900,
        first_seen=100.0,
        activity=True,
    )
    assert hold_r is False
    assert tag_r == "ready"

    hold_t, tag_t = fuel_chain.mrb_coderabbit_offer(
        row,
        now=100.0 + 901.0,
        enabled=True,
        has_review=False,
        wait_s=900,
        first_seen=100.0,
        activity=True,
    )
    assert hold_t is False
    assert tag_t == "timeout"


def test_format_assign_line_appends_coderabbit_timeout():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#5390",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/5390",
        "coderabbit": "timeout",
        "review": "full",
    }
    line = gitclaim.format_assign_line("flamingo-1", row)
    assert line.startswith("flamingo-1: MRB SimonBarnett/bobiverse#5390 https://")
    assert "coderabbit=timeout" in line
    assert "review=full" in line


def test_shop_listen_keeps_done_url_with_cr_counters():
    parsed = shop_listen.parse_shop_job_line(
        "DONE MRB SimonBarnett/bobiverse#5390 PASS "
        "https://github.com/SimonBarnett/bobiverse/pull/5390 "
        "cr_findings=4 confirmed=1 fp=2"
    )
    assert parsed is not None
    assert parsed.result == "PASS"
    assert parsed.url == "https://github.com/SimonBarnett/bobiverse/pull/5390"
    assert shop_listen.mrb_cr_counters(parsed.rest) == {
        "cr_findings": 4,
        "confirmed": 1,
        "fp": 2,
    }
