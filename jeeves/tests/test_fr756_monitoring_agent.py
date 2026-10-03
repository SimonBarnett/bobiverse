"""FR #756: Jeeves install ships a MONITORING-agent AGENTS/GROK/skills layer.

An agent with CWD <ai root>\\jeeves is the monitoring overlay for the deterministic
chair: keep work flowing to workers, report delays via intake (de-duped), never act
as chair / never !assign / never touch Ergo.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

JEEVES = REPO / "jeeves"
AGENTS = JEEVES / "AGENTS.md"
SKILLS = JEEVES / ".grok" / "skills"
COMMON_SKILLS = REPO / "common" / ".grok" / "skills"

IMPERATIVE_HEADING = "Keep the flow of work to the workers going"
IMPERATIVE_MARK = "Keep the flow of work to the workers going"
DELAY_CUES = (
    "idle seat",
    "empty offer queue",
    "GIVEUP",
    "stale digest",
    "self-review",
    "stuck accepted",
    "webhooks",
)
ROLE_MARKS = (
    "MONITORING",
    "not the chair",
    "not a worker",
)
NEVER_MARKS = (
    "never !assign",
    "never !focus",
    "Ergo",
    "BobIrcd",
    "no secrets",
)
INTAKE_MARKS = (
    "Report-BobiverseIntakeIssue.ps1",
    "de-duplicat",
    "/bob/v1/intake",
)
FLOW_MARKS = (
    "FR",
    "MRB",
    "UAT",
    "!bored",
    "ACK",
    "DONE",
)
DIGEST_MARKS = (
    "digest",
    "idle",
    "offered",
    "doing",
)
IRC_MARKS = (
    "#bobiverse",
    "#{machine}",
    "worker",
)
CAST_IRON = "CAST IRON RULE - HARVEST AND FILE EVERYTHING"
HARVEST_MARKS = (
    "Invoke-BobiverseHarvest.ps1",
    "Report-BobiverseIntakeIssue.ps1",
    "https://irc.ntsa.uk/bob/v1/intake",
)

REQUIRED_SKILL_BOOKS = (
    "bobiverse-jeeves",
    "bobiverse-jeeves-commands",
    "bobiverse-jeeves-troubleshooting",
    "bobiverse-jeeves-monitor",
)
SHARED_BOOKS = ("bobiverse-fleet-ops", "harvest", "harvest-agent-skills")

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def _first_section_heading(text: str) -> str | None:
    m = re.search(r"^##\s+(.+)$", _norm(text), re.M)
    return m.group(1).strip() if m else None


def _jeeves_skill_files() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


def test_agents_md_exists_and_imperative_is_first_section():
    assert AGENTS.is_file()
    t = AGENTS.read_text(encoding="utf-8-sig")
    assert _first_section_heading(t) == IMPERATIVE_HEADING
    assert IMPERATIVE_MARK in t
    for cue in DELAY_CUES:
        assert cue.lower() in t.lower(), cue


def test_agents_md_states_monitoring_role_and_never_chair():
    t = AGENTS.read_text(encoding="utf-8-sig").lower()
    for mk in ROLE_MARKS:
        assert mk.lower() in t, mk
    for mk in NEVER_MARKS:
        assert mk.lower() in t, mk
    for mk in INTAKE_MARKS:
        assert mk.lower() in t, mk


def test_agents_md_covers_flow_digest_irc_and_commands():
    t = AGENTS.read_text(encoding="utf-8-sig")
    for mk in FLOW_MARKS + DIGEST_MARKS + IRC_MARKS:
        assert mk.lower() in t.lower(), mk
    assert "docs/jeeves-commands.md" in t or "jeeves-commands.md" in t
    assert ".grok/skills/bobiverse-jeeves-monitor/SKILL.md" in t
    assert ".grok/skills/harvest/SKILL.md" in t
    assert CAST_IRON in t
    for mk in HARVEST_MARKS:
        assert mk in t, mk


def test_required_skill_books_exist_with_imperative_first():
    for name in REQUIRED_SKILL_BOOKS:
        p = SKILLS / name / "SKILL.md"
        assert p.is_file(), name
        t = p.read_text(encoding="utf-8-sig")
        assert _first_section_heading(t) == IMPERATIVE_HEADING, name
        assert IMPERATIVE_MARK in t
        assert CAST_IRON in t
        for mk in HARVEST_MARKS:
            assert mk in t, (name, mk)


def test_monitor_skill_covers_full_jeeves_spec():
    t = (SKILLS / "bobiverse-jeeves-monitor" / "SKILL.md").read_text(encoding="utf-8-sig")
    for mk in (
        "architecture",
        "queue",
        "focus",
        "assign",
        "seat",
        "FR",
        "MRB",
        "UAT",
        "digest",
        "idle",
        "offered",
        "doing",
        "!assign",
        "!focus",
        "intake",
        "de-duplicat",
        "#bobiverse",
        "Ergo",
        "BobIrcd",
        "jeeves-commands.md",
    ):
        assert mk.lower() in t.lower(), mk


def test_shared_harvest_skills_exist_for_msi_merge():
    for name in SHARED_BOOKS:
        assert (COMMON_SKILLS / name / "SKILL.md").is_file(), name


def test_common_harvest_skill_has_cast_iron_and_imperative_or_pointer():
    """Harvest is shared; FR #756 requires harvest in the Jeeves package (merged at pack)."""
    t = (COMMON_SKILLS / "harvest" / "SKILL.md").read_text(encoding="utf-8-sig")
    assert CAST_IRON in t
    assert "Invoke-BobiverseHarvest.ps1" in t
    assert "Report-BobiverseIntakeIssue.ps1" in t


@WIN
def test_pack_stages_monitoring_agent_layer_for_jeeves(tmp_path):
    out = tmp_path / "dist"
    run = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "Pack-BobiverseRelease.ps1"),
            "-Product",
            "jeeves",
            "-SkipMsi",
            "-KeepStage",
            "-SkipWorkerExe",
            "-OutDir",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, (run.stdout[-2000:] + run.stderr[-2000:])
    ver = (ROOT / "src" / "VERSION").read_text(encoding="utf-8").strip()
    stage = out / f"jeeves-{ver}"
    assert stage.is_dir(), list(out.iterdir())
    for f in ("AGENTS.md", "CLAUDE.md", "GROK.md", ".cursor/rules/bobiverse-jeeves.mdc"):
        p = stage / f
        assert p.is_file(), f
        t = p.read_text(encoding="utf-8-sig")
        assert _first_section_heading(t) == IMPERATIVE_HEADING, f
        assert IMPERATIVE_MARK in t
        assert CAST_IRON in t
        for mk in ROLE_MARKS:
            assert mk.lower() in t.lower(), (f, mk)
    for book in list(REQUIRED_SKILL_BOOKS) + list(SHARED_BOOKS):
        sk = stage / ".grok" / "skills" / book / "SKILL.md"
        assert sk.is_file(), book
    mon = (stage / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )
    assert _first_section_heading(mon) == IMPERATIVE_HEADING
    assert (stage / "docs" / "jeeves-commands.md").is_file()
    assert (stage / "scripts" / "Report-BobiverseIntakeIssue.ps1").is_file()
    assert (stage / "scripts" / "Invoke-BobiverseHarvest.ps1").is_file()
