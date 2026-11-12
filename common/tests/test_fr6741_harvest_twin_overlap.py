"""FR #6741: harvest twin skip must not fire on two shared distinctive tokens.

A skills-visionary how-to-plan lesson was SKIPPED as lesson_already_covered
because Test-HarvestLessonDistinctiveOverlap treated any two overlapping
tokens as a twin. Require a shared phrase (3 consecutive distinctive tokens)
or >=5 shared tokens. SKIPPED lines must cite the covering PR url.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
    HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

PLAN_LESSON = (
    "how-to-plan: plan-folder fetch cwd, and a Shape line that must be exactly LOCKED"
)
OTHER_PR_BLOB = (
    "lesson(harvest-skills-visionary): Fixture-only probes stay green\n"
    "Session summary:\nseat harvest fetch secrets on entry box\n"
    "Lessons:\n- Fixture-only /selftest probes must not require vendor secrets\n"
    "https://github.com/SimonBarnett/skills-visionary/pull/99"
)
SAME_PHRASE_BLOB = (
    "Lessons:\n- how-to-plan: plan-folder fetch cwd, and a Shape line that must be exactly LOCKED\n"
)
FIVE_TOKEN_LESSON = "alpha bravo charlie delta echo foxtrot golf"
FIVE_TOKEN_BLOB = "alpha bravo charlie delta echo extra noise"


def _extract_fn(name: str, until: str) -> str:
    text = HARVEST.read_text(encoding="utf-8-sig")
    m = re.search(
        rf"(function {re.escape(name)}\b[\s\S]*?)(?=\nfunction {re.escape(until)}\b)",
        text,
    )
    assert m, f"missing {name} before {until} in {HARVEST}"
    return m.group(1)


def _ps_overlap(existing: str, new: str) -> bool:
    fn = _extract_fn(
        "Test-HarvestLessonDistinctiveOverlap", "Test-HarvestPrCoversLesson"
    )
    script = (
        fn
        + "\n$r = Test-HarvestLessonDistinctiveOverlap -ExistingBlob $env:EXISTING -NewLesson $env:NEWL\n"
        + "if ($r) { 'TRUE' } else { 'FALSE' }\n"
    )
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["EXISTING"] = existing
    env["NEWL"] = new
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "").strip().splitlines()
    assert proc.returncode == 0, proc.stderr
    assert out, proc.stderr
    return out[-1].strip().upper() == "TRUE"


def test_two_shared_tokens_are_not_a_twin():
    assert not _ps_overlap(OTHER_PR_BLOB, PLAN_LESSON)


def test_shared_phrase_is_a_twin():
    assert _ps_overlap(SAME_PHRASE_BLOB, PLAN_LESSON)


def test_five_shared_tokens_are_a_twin():
    assert _ps_overlap(FIVE_TOKEN_BLOB, FIVE_TOKEN_LESSON)


def test_skip_line_cites_covering_pr_url():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #6741" in text
    assert "shared -ge 5" in text or "shared -ge 5" in text.replace(" ", "")
    assert "SKIPPED harvest open lesson twin" in text
    assert "$openTwinUrl" in text or "covering PR" in text.lower()
    # The skip host line must interpolate a url (https:// or $...url)
    assert re.search(
        r"SKIPPED harvest open lesson twin[^\n]*(\$openTwinUrl|\$twinUrl|https://github\.com)",
        text,
    )
