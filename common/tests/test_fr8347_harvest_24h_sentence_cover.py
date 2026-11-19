"""FR #8347: a 24h harvest-lesson PR covers a lesson only by its sentence."""
from __future__ import annotations

import os
import re
import subprocess

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"

LESSON = (
    "Seed skill-dag resolve with the job type token (FR, MRB, UAT, or FIX). "
    "A seed of owner/repo#N returns an empty match."
)
UNRELATED = """MRB (light triage): useful.

Lessons:
- When opencode_typed_delivery is called without closes_ref, strip the leading FR|MRB|UAT|FIX token from the job key so Closes/DONE do not double the task type.

---
"""


def _sentence_only(title: str, body: str, lesson: str) -> bool:
    text = HARVEST.read_text(encoding="utf-8-sig")
    m = re.search(
        r"(function Get-HarvestLessonTitleStem\b[\s\S]*?)(?=\nfunction Test-HarvestOpenLessonTwin\b)",
        text,
    )
    assert m, "lesson matchers missing"
    script = (
        m.group(1)
        + "\n$r = Test-HarvestPrCoversLesson -PrTitle $env:PRT -PrBody $env:PRB "
        + "-LessonLines @($env:LES) -SentenceOnly\n"
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


def test_unrelated_24h_pr_is_not_a_cover():
    title = (
        "lesson(harvest): When opencode_typed_delivery is called without closes_ref, "
        "strip the lea..."
    )
    assert _sentence_only(title, UNRELATED, LESSON) is False


def test_same_sentence_is_a_24h_cover():
    body = "Lessons:\n- " + LESSON + "\n"
    assert _sentence_only("lesson(harvest): " + LESSON[:70], body, LESSON) is True


def test_recent_dedup_uses_sentence_only():
    text = HARVEST.read_text(encoding="utf-8-sig")
    start = text.index("function Test-HarvestRecentLessonDedup")
    chunk = text[start:start + 1800]
    assert "-SentenceOnly" in chunk
