"""Harvest #2296: MRB harvest-promote merge order (skill first, then docs/mrb from new main)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr2296_job_mrb_harvest_promote_order():
    text = MRB.read_text(encoding="utf-8")
    assert "2296" in text
    assert "merge the **skill/promote PR first**" in text or "merge skill PR first" in text.lower()
    assert "docs/mrb" in text
    assert "new" in text.lower() and "origin/main" in text
    assert "DONE PASS" in text or "DONE" in text
    assert not MRB.read_bytes().startswith(b"\xef\xbb\xbf")
    assert MRB.read_bytes().endswith(b"\n")


def test_fr2296_harvest_log():
    log = LOG.read_text(encoding="utf-8")
    assert "2296" in log
    assert "2289" in log
    assert "docs/mrb" in log.lower() or "docs/mrb-N" in log
