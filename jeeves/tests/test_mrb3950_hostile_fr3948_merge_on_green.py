"""Hostile MRB #3950 / FR #3948: short-SHA match, chair drain wiring, skill + shop_listen pins."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")


FULL = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHORT = FULL[:12]


def test_shas_match_short_prefix_allows_merge_decision():
    assert mrb_merge_on_green.shas_match(SHORT, FULL)
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha=SHORT,
            current_sha=FULL,
            checks="success",
        )
        == "merge"
    )


def test_shas_match_rejects_different_prefix():
    assert not mrb_merge_on_green.shas_match("cccccccc", FULL)
    assert (
        mrb_merge_on_green.decide_merge_on_green(
            pass_sha="cccccccccccc",
            current_sha=FULL,
            checks="success",
        )
        == "requeue_sha"
    )


def test_chair_health_drains_merge_on_green():
    text = (ROOT / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    assert "MERGE_ON_GREEN_S = 60.0" in text
    assert "mrb_merge_on_green.process_pending" in text
    assert "next_merge_on_green" in text


def test_shop_listen_enqueues_on_done_mrb_pass():
    text = (ROOT / "common" / "scripts" / "shop_listen.py").read_text(encoding="utf-8")
    assert "FR #3948" in text
    assert "enqueue_from_done" in text
    assert "merge_on_green" in text


def test_job_mrb_skill_cast_iron_fr3948_contiguous():
    skill = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #3948 - hand off after push; never poll CI (durable)" in skill
    assert "Never poll or watch CI to completion" in skill
    assert "gh pr checks --watch" in skill
    assert "merge-on-green pending" in skill
    assert "mrb_merge_on_green" in skill
    # UTF-8 no BOM
    raw = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
