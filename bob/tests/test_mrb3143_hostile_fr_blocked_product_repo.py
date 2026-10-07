"""MRB #3143 hostile: FR blocked-on-missing-product-repo playbook in job-fr, not harvest."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOB_FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb3143_job_fr_has_product_repo_gate():
    raw = JOB_FR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Product repo not created yet" in text
    assert "plan-git-from-plan" in text
    assert "Do not create the repo" in text or "do **not** create the repo" in text.lower()
    assert "GIVEUP" in text
    assert "leave the issue" in text.lower() or "Leave the issue" in text


def test_mrb3143_harvest_does_not_park_product_repo_gate():
    text = HARVEST.read_text(encoding="utf-8")
    assert "FR blocked on product repo: when Fix says After repo create" not in text
