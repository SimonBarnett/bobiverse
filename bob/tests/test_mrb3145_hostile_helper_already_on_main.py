"""MRB #3145 hostile: helper-already-on-main / env synth playbook in job-mrb, not harvest."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOB_MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb3145_job_mrb_has_helper_already_on_main_playbook():
    raw = JOB_MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Helper already on main" in text
    assert "docs + dedicated-tests" in text or "docs+dedicated" in text.replace(" ", "")
    assert "origin/main" in text
    assert "aws-cdk" in text or "npx cdk" in text


def test_mrb3145_harvest_does_not_park_a_search_mrb_tip():
    text = HARVEST.read_text(encoding="utf-8")
    assert "a-search MRB: when FR-034 helper already merged via FR-032" not in text
