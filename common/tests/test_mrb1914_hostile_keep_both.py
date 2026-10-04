"""MRB #1914 hostile: keep-both phrases + no real conflict markers after rebase fix."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _clean(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        assert not s.startswith("<<<<<<<"), (path, i)
        assert not s.startswith(">>>>>>>"), (path, i)
    return text


def test_mrb1914_hostile_keep_both_on_main_tip():
    h = _clean(HARVEST)
    m = _clean(MRB)
    log = _clean(LOG)
    assert "skill-harvest-log parallel promotes" in h
    assert "keep both dated sections" in h
    assert "1757" in h and "1750" in h
    assert "keep both dated sections" in m
    assert "1757" in m
    assert "1757" in log
    assert "keep both dated sections" in log
    assert "BobCallback multi-supervisor refuse" in log or "1767" in log
