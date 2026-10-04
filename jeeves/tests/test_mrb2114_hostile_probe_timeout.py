"""MRB #2114 hostile: report probe >=20s + keep-both harvest-log."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "jeeves/scripts/Watch-BobWebhooks.ps1"
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _clean(path: Path) -> str:
    raw = path.read_bytes()
    # .ps1 may have UTF-8 BOM
    text = raw.decode("utf-8-sig")
    if path.suffix.lower() == ".ps1":
        # WinPS: BOM OK when non-ASCII present
        pass
    else:
        assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert text.endswith("\n"), path
    for i, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        assert not s.startswith("<<<<<<<"), (path, i)
        assert not s.startswith(">>>>>>>"), (path, i)
    return text


def test_mrb2114_hostile_probe_timeout():
    w = _clean(WATCH)
    m = _clean(MON)
    t = _clean(TROUBLE)
    log = _clean(LOG)
    assert "TimeoutSec 20" in w and "TimeoutSec 8" not in w
    assert "2057" in m and "20" in m
    assert "2057" in t and "max-time" in t
    assert "2057" in log
    # keep-both: prior linked_existing or living FR sections still present
    assert "1812" in log or "2001" in log or "linked_existing" in log
