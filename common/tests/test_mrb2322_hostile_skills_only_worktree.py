"""MRB #2322 hostile: harvest #2318 skills-only worktree playbook (no mojibake)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
MOJIBAKE = ("â€¦", "â†’", "â€”", "â€“", "Ã¢")


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path


def test_mrb2322_skills_only_section_clean_utf8():
    text = HAS.read_text(encoding="utf-8")
    _no_bom(HAS)
    assert "2318" in text
    assert "origin/main" in text
    assert "worktree" in text.lower()
    assert "gitclaim" in text.lower()
    assert "bobcallback" in text.lower()
    assert "`obcallback" not in text  # PR tip typo; must say bobcallback
    for bad in MOJIBAKE:
        assert bad not in text, f"mojibake/typo {bad!r}"
    assert "Skills-only promote from worktree" in text


def test_mrb2322_harvest_log_keep_both():
    log = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "2318" in log
    assert "2317" in log
    # keep-both with parallel main lessons
    assert "2179" in log or "WHOIS" in log
    assert "<<<<<<<" not in log and ">>>>>>>" not in log
    for bad in ("â€¦", "â†’", "Ã¢"):
        assert bad not in log
