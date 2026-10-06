"""MRB #2763 hostile: digest audit-path playbook lives in job-mrb, not harvest."""
from __future__ import annotations

from pathlib import Path

JOB_MRB = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)
HARVEST = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2763_job_mrb_has_digest_audit_path_under_harvest_digest():
    text = _utf8_no_bom(JOB_MRB)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "**Digest audit path" in text
    idx = text.index("**Digest audit path")
    window = text[idx : idx + 420]
    assert "harvest-lessons-audit-2026-10-06.md" in window
    assert "docs/mrb-N" in window
    assert "2717" in window
    assert "dead" in window.lower() or "never on main" in window
    # Sits inside Harvest digest before Self-MRB digest bullet
    digest = text.index("## Harvest digest")
    self_mrb_bullet = text.index("- **Self-MRB is per seat", digest)
    assert digest < idx < self_mrb_bullet


def test_mrb2763_harvest_lacks_raw_digest_audit_bullet():
    text = _utf8_no_bom(HARVEST)
    # Harvest may cite the audit filename in its own digest intro; the job-mrb playbook
    # must not be duplicated as a raw "- Harvest-digest skill PRs" bullet here.
    assert "- Harvest-digest skill PRs" not in text
    assert "**Digest audit path" not in text
