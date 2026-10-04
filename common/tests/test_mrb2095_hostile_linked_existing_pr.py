"""MRB #2095 hostile: linked_existing_pr playbook + keep-both log."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HV = ROOT / "common/.grok/skills/harvest/SKILL.md"
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


def test_mrb2095_hostile_linked_existing_pr():
    h = _clean(HV)
    a = _clean(HAS)
    log = _clean(LOG)
    assert "linked_existing_pr" in h and "1812" in h and "2013" in h
    assert "harvest_pr_summary" in h or "draft_pr_error" in h
    assert "linked_existing_pr" in a
    assert "linked_existing_pr" in log
    # keep-both: product FR #1812 log section still present
    assert "Harvest intake links existing PR (FR #1812)" in log or "FR #1812)" in log
