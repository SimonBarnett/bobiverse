"""MRB #2091 hostile: living FR re-file keep-both + no conflict markers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
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


def test_mrb2091_hostile_living_fr_on_main_tip():
    h = _clean(HARVEST)
    a = _clean(HAS)
    log = _clean(LOG)
    assert "2001" in h and "living" in h.lower()
    assert "feature-request" in h
    assert "1993" in h
    assert "2001" in a and "feature-request" in a
    assert "2001" in log
    assert "keep-both" in log or "1757" in log or "Quiet MSI" in log
