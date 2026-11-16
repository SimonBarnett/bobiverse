"""FR #7903: an open harvest-lesson PR covers a tip only when the lesson sentence matches."""
from __future__ import annotations

import os
import re
import subprocess

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
    HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

WEDGE = (
    "When the worker launches a helper by path, do not hand external python "
    "a PyInstaller _MEI script path"
)
CONSOLE_TITLE = (
    "lesson(bobiverse-bob-worker): Windows console-close 3221225786 is "
    "STATUS_CONTROL_C_EXIT, not an agent crash"
)
CONSOLE_BODY = """Session summary:
console close

Lessons:
- A Windows console-close exit 3221225786 is STATUS_CONTROL_C_EXIT, not an agent crash

SKILL.md
- do not hand external python a PyInstaller helper when the worker launches a script path
- opencode python script path worker external pyinstaller mei helper launch install
"""


def _covers(title: str, body: str, lesson: str) -> bool:
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


def test_unrelated_open_lesson_pr_is_not_a_twin():
    assert _covers(CONSOLE_TITLE, CONSOLE_BODY, WEDGE) is False


def test_same_lesson_sentence_is_a_twin():
    body = "Session summary:\nwedge\n\nLessons:\n- " + WEDGE + "\n"
    assert _covers("lesson(bobiverse-bob-worker): " + WEDGE[:60], body, WEDGE) is True


def test_skill_paste_without_the_sentence_is_not_enough():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #7903" in text
    assert "Get-HarvestPrLessonSentences" in text
