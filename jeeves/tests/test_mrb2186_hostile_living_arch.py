"""MRB #2186 hostile: living ionos arch FR playbook; do not close #1993."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md"
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


def test_mrb2186_hostile_living_arch():
    j = _clean(JEEVES)
    log = _clean(LOG)
    assert "1989" in j and "1993" in j
    assert "require_machine" in j
    assert "1989" in log and "1993" in log
    # keep-both: prior dated sections remain
    assert "2057" in log or "1812" in log or "2001" in log
