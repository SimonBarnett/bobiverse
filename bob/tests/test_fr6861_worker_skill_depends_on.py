"""FR #6861: worker core skills declare depends_on edges (no UAT on FR)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOB = ROOT / "bob"
COMMON = ROOT / "common"

SKILLS = {
    "bobiverse-worker-seat": BOB
    / "agents"
    / "worker"
    / ".grok"
    / "skills"
    / "bobiverse-worker-seat"
    / "SKILL.md",
    "bobiverse-bob-job-irc": BOB / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md",
    "bobiverse-bob-job-fr": BOB / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md",
    "bobiverse-bob-job-mrb": BOB / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md",
    "bobiverse-bob-job-uat": BOB / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md",
    "harvest": COMMON / ".grok" / "skills" / "harvest" / "SKILL.md",
    "harvest-agent-skills": COMMON / ".grok" / "skills" / "harvest-agent-skills" / "SKILL.md",
}


def _frontmatter(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"no YAML frontmatter in {path}"
    return m.group(1)


def _depends_on(fm: str) -> list[str]:
    # depends_on: []  OR
    # depends_on:
    #   - id
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


@pytest.mark.parametrize("name", sorted(SKILLS))
def test_fr6861_core_skill_frontmatter_parses(name):
    path = SKILLS[name]
    assert path.is_file(), path
    fm = _frontmatter(path)
    assert re.search(r"(?m)^name:\s+" + re.escape(name) + r"\s*$", fm)
    deps = _depends_on(fm)
    assert "depends_on:" in fm
    for d in deps:
        assert d in SKILLS or d.startswith("bobiverse-"), d


def test_fr6861_job_fr_lists_job_irc_not_uat():
    deps = _depends_on(_frontmatter(SKILLS["bobiverse-bob-job-fr"]))
    assert "bobiverse-bob-job-irc" in deps
    assert "bobiverse-bob-job-uat" not in deps


def test_fr6861_job_fr_ancestors_exclude_uat():
    """Transitive depends_on of job-fr must not include UAT (S2 fixture for later MCP)."""
    seen: set[str] = set()
    stack = ["bobiverse-bob-job-fr"]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if cur not in SKILLS:
            continue
        for d in _depends_on(_frontmatter(SKILLS[cur])):
            stack.append(d)
    assert "bobiverse-bob-job-irc" in seen
    assert "bobiverse-bob-job-uat" not in seen
