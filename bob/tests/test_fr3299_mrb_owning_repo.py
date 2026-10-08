"""FR #3299: MRB harvest/skill PRs check owning repo (re-file / MOVED / hold-open)."""
from __future__ import annotations

from pathlib import Path

JOB_MRB = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
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


def test_fr3299_job_mrb_step0_owning_repo_contiguous():
    """Step 0 sits before step 1 and carries the owning-repo / re-file / hold-open contract."""
    text = _utf8_no_bom(JOB_MRB)
    section_start = text.index("## Harvest-lesson intake PRs")
    section_end = text.index("## Skill / markdown diff hygiene")
    section = text[section_start:section_end]

    assert "0. **Who owns this lesson (owning repo)?**" in section
    step0_idx = section.index("0. **Who owns this lesson (owning repo)?**")
    step1_idx = section.index("\n1. Verify each lesson is generalised")
    assert step0_idx < step1_idx
    step0 = section[step0_idx:step1_idx]

    # Contiguous acceptance phrases from FR #3299.
    assert "owning repo" in step0
    assert "re-file" in step0
    assert "Moved to" in step0
    assert "leave the original" in step0 and "OPEN" in step0
    assert "never" in step0.lower() and "FAIL" in step0
    assert "MOVED" in step0


def test_fr3299_step8_and_conflicting_point_at_step0():
    """Wrong-book / CONFLICTING exits must cite step 0 (no FAIL-close without a skill-book link)."""
    text = _utf8_no_bom(JOB_MRB)

    # Step 8 wrong-book paragraph.
    assert "Wrong-book bob-worker product lesson" in text
    idx8 = text.index("Wrong-book bob-worker product lesson")
    window8 = text[idx8 : idx8 + 700]
    assert "step 0" in window8
    assert "never FAIL-close without that link" in window8 or "skill-book" in window8

    # CONFLICTING / superseded harvest-lesson twins + wrong-repo.
    assert "## CONFLICTING / superseded MRB" in text
    conf = text[
        text.index("## CONFLICTING / superseded MRB") : text.index("## Fix-PR race after DONE")
    ]
    assert "step 0" in conf
    assert "Wrong-**repo**" in conf or "Wrong-repo" in conf or "wrong-**repo**" in conf.lower()
    assert "MOVED" in conf or "re-file" in conf
    assert "never FAIL-close without a skill-book link" in conf
