"""FR #8090: MRB checkout when another seat already holds the PR head branch.

Pins bobiverse-bob-job-mrb: do not steal a sibling worktree; add a local
review branch at the same headRefOid and still require HEAD == headRefOid.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", f"BOM in {path}"
    return raw.decode("utf-8")


def test_fr8090_mrb_skill_busy_head_branch_fallback():
    t = _read(MRB)
    assert "FR #8090" in t
    assert "FR #8022" in t
    assert "headRefOid" in t
    assert "already used by worktree" in t.lower()
    low = t.lower()
    assert "do not" in low or "never" in low
    assert "steal" in low or "sibling" in low or "reuse the sibling" in low
    assert "mrb-n-review" in low or "local branch" in low
    assert "rev-parse head" in low
