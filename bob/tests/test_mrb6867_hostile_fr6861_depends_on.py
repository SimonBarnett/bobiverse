"""MRB #6867 hostile pin for FR #6861 depends_on edges."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOB = ROOT / "bob"
COMMON = ROOT / "common"


def _frontmatter(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"no YAML frontmatter in {path}"
    return m.group(1)


def _depends_on(fm: str) -> list[str]:
    m = re.search(r"(?m)^depends_on:\s*\[(.*)\]\s*$", fm)
    if m:
        inner = m.group(1).strip()
        if not inner:
            return []
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
    m = re.search(r"(?m)^depends_on:\s*\n((?:  - .+\n)*)", fm + "\n")
    if not m:
        return []
    return re.findall(r"(?m)^  - (\S+)\s*$", m.group(1))


def test_mrb6867_harvest_root_empty_depends():
    assert _depends_on(_frontmatter(COMMON / ".grok/skills/harvest/SKILL.md")) == []


def test_mrb6867_harvest_agent_skills_depends_on_harvest():
    deps = _depends_on(_frontmatter(COMMON / ".grok/skills/harvest-agent-skills/SKILL.md"))
    assert "harvest" in deps


def test_mrb6867_worker_seat_depends_on_irc_and_harvest():
    deps = _depends_on(
        _frontmatter(BOB / "agents/worker/.grok/skills/bobiverse-worker-seat/SKILL.md")
    )
    assert "bobiverse-bob-job-irc" in deps
    assert "harvest" in deps


def test_mrb6867_job_mrb_and_uat_depend_on_irc_not_fr():
    mrb = _depends_on(_frontmatter(BOB / ".grok/skills/bobiverse-bob-job-mrb/SKILL.md"))
    uat = _depends_on(_frontmatter(BOB / ".grok/skills/bobiverse-bob-job-uat/SKILL.md"))
    assert "bobiverse-bob-job-irc" in mrb
    assert "bobiverse-bob-job-irc" in uat
    assert "bobiverse-bob-job-fr" not in mrb
    assert "bobiverse-bob-job-uat" not in mrb
    assert "bobiverse-bob-job-fr" not in uat
