"""FR #905: harvest/skill intake playbooks are not FR jobs; twin-FR playbook lives in skills."""
from __future__ import annotations

from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


def test_harvest_title_skips_fr905_shape():
    why = gitclaim.issue_skip_fr_reason(
        title="harvest: FR #751 DONE existing #867; older closed-PR-as-FR twin of #838/#846",
        body="Older open FRs that restated closed-PR-as-FR…",
        labels=("via-intake",),
    )
    assert why == "harvest_title"


def test_skill_label_skips_even_without_harvest_prefix():
    why = gitclaim.issue_skip_fr_reason(
        title="FR #751 twin playbook",
        body="x",
        labels=("skill", "via-intake"),
    )
    assert why == "label:skill"


def test_job_fr_skill_documents_twin_already_fixed():
    text = SKILL.read_text(encoding="utf-8")
    assert "Twin / already-fixed" in text or "already-fixed FRs" in text
    assert "DONE" in text and "existing" in text.lower()
