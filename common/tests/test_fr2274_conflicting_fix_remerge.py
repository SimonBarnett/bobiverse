"""Harvest #2274: CONFLICTING fix PR must re-merge main keep-both before REST merge."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

LOG = ROOT / "common/docs/skill-harvest-log.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"


def test_fr2274_harvest_log_nested_remerge():
    text = LOG.read_text(encoding="utf-8")
    assert "2274" in text
    assert "keep-both" in text.lower() or "keep both" in text.lower()
    assert "REST" in text or "gh pr merge" in text
    assert not text.startswith("\ufeff")
    assert LOG.read_bytes().endswith(b"\n")


def test_fr2274_job_mrb_and_harvest_skills():
    mrb = MRB.read_text(encoding="utf-8")
    has = HAS.read_text(encoding="utf-8")
    assert "2274" in mrb and "2274" in has
    assert "keep-both again" in mrb.lower() or "keep both again" in mrb.lower()
    assert "keep-both again" in has.lower() or "keep both again" in has.lower()
    assert "see bobiverse-bob-job-mrb CONFLICTING" in has
    assert "\bobiverse" not in has  # no stray control-char before bobiverse
