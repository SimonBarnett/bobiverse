"""FR #7962: harvest twin skip must not fire on shared OpenCode/pause vocabulary.

Live incident: after MRB #7957 (FR #7952: pause fallback returns to the
configured model), Invoke-BobiverseHarvest -Repo SimonBarnett/bobiverse skipped
filing because the open harvest-lesson PR #7954 ("A hard ceiling or watchdog
kill is not out of fuel", FR #7951) shares the OpenCode/pause/record/turn
mechanism words. Different FR id, different acceptance - shared context must not
read as a distinctive twin.

Fix: treat opencode/pause/model/fuel/record/turn/call/fallback/configured/next/
job/json/text/return/returns/write as domain-generic twin tokens (PowerShell and
intake), and guard the PowerShell distinctive-overlap when a lesson tokenizes to
nothing (all-generic lesson).
"""
from __future__ import annotations

import os
import re
import subprocess

import intake

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
    HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

CEILING_TITLE = (
    "lesson(harvest): A hard ceiling or watchdog kill is not out of fuel. "
    "Do not call record-p..."
)
CEILING_LESSON = (
    "A hard ceiling or watchdog kill is not out of fuel. Do not call record-pause "
    "for that turn, and do not write opencode-pauses.json from ceiling text."
)
PAUSE_FALLBACK_LESSON = (
    "OpenCode pause fallback: do not call record-pause for that turn; "
    "return to the configured model on the next job"
)


def _ceiling_body() -> str:
    return (
        "MRB (light triage): is the lesson useful, generalised, non-duplicate...\n\n"
        "Target skill book: `harvest` (`common/.grok/skills/harvest/SKILL.md`).\n\n"
        "Lessons:\n- "
        + CEILING_LESSON
        + "\n\n---\n\n"
        "Session summary:\n"
        "FR #7951: hard-ceiling and watchdog text no longer writes an OpenCode model pause.\n"
    )


def _ps_covers(title: str, body: str, lesson: str) -> bool:
    text = HARVEST.read_text(encoding="utf-8-sig")
    m = re.search(
        r"(function Get-HarvestLessonTitleStem\b[\s\S]*?)(?=\nfunction Test-HarvestOpenLessonTwin\b)",
        text,
    )
    assert m, "lesson matchers missing"
    script = (
        m.group(1)
        + "\n$r = Test-HarvestPrCoversLesson -PrTitle $env:PRT -PrBody $env:PRB -LessonLines @($env:LES)\n"
        + "if ($r) { 'TRUE' } else { 'FALSE' }\n"
    )
    env = dict(os.environ)
    env["PRT"] = title
    env["PRB"] = body
    env["LES"] = lesson
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = (proc.stdout or "").strip().splitlines()
    assert out, proc.stderr
    return out[-1].strip().upper() == "TRUE"


def test_pause_fallback_lesson_is_not_a_ceiling_twin():
    assert _ps_covers(CEILING_TITLE, _ceiling_body(), PAUSE_FALLBACK_LESSON) is False


def test_identical_ceiling_lesson_is_still_a_twin():
    assert _ps_covers(CEILING_TITLE, _ceiling_body(), CEILING_LESSON) is True


def test_intake_pause_fallback_not_a_ceiling_twin():
    assert not intake.harvest_pr_covers_new_lesson(
        CEILING_TITLE,
        CEILING_LESSON,
        PAUSE_FALLBACK_LESSON,
        new_title="lesson(harvest): pause fallback returns to configured model",
    )


def test_intake_identical_ceiling_lesson_still_a_twin():
    assert intake.harvest_pr_covers_new_lesson(
        CEILING_TITLE,
        CEILING_LESSON,
        CEILING_LESSON,
    )


def test_fr7962_generic_tokens_pinned():
    for tok in (
        "opencode",
        "pause",
        "pauses",
        "model",
        "fuel",
        "record",
        "turn",
        "call",
        "fallback",
        "configur",
        "next",
        "job",
        "json",
        "text",
    ):
        assert tok in intake._HARVEST_GENERIC_TOKENS, tok
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #7962" in text
    assert "'opencode'" in text and "'pause'" in text
    assert "$a -and $b" in text
