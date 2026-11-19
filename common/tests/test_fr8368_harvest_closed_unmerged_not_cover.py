"""FR #8368: a closed unmerged (MRB-rejected) harvest-lesson must not cover a corrected lesson.

PR 726 was closed unmerged because its bullet said "UPD+" / "use EFORM" for a
procedure-prep lesson, but the corrected gate is UPD=N + d{exec}.prp and forbids
EFORM for TYPE=P. The 24h dedup still counted that rejected tip as a cover for
the corrected sentence. A closed unmerged lesson must not count as a cover.
"""
from __future__ import annotations

import os
import re
import subprocess

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _extract_fn(name: str, until: str) -> str:
    text = HARVEST.read_text(encoding="utf-8-sig")
    m = re.search(
        rf"(function {re.escape(name)}\b[\s\S]*?)(?=\nfunction {re.escape(until)}\b)",
        text,
    )
    assert m, f"missing {name} before {until} in {HARVEST}"
    return m.group(1)


def _ps_closed_unmerged(state: str, merged_at: str | None) -> bool:
    fn = _extract_fn("Test-HarvestPrClosedUnmerged", "Test-HarvestRecentLessonDedup")
    script = (
        fn
        + "\n$o = [pscustomobject]@{ state = $env:PSTATE; mergedAt = $env:PMERGED }\n"
        + "if ($env:PMERGED -eq '') { $o.mergedAt = $null }\n"
        + "$r = Test-HarvestPrClosedUnmerged -Pr $o\n"
        + "if ($r) { 'TRUE' } else { 'FALSE' }\n"
    )
    env = dict(os.environ)
    env["PSTATE"] = state
    env["PMERGED"] = merged_at or ""
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


def test_closed_unmerged_pr_is_not_a_cover():
    assert _ps_closed_unmerged("CLOSED", None) is True


def test_open_pr_is_not_skipped():
    assert _ps_closed_unmerged("OPEN", None) is False


def test_merged_pr_is_not_skipped():
    assert _ps_closed_unmerged("MERGED", "2026-11-19T13:40:43Z") is False


def test_recent_dedup_queries_state_and_merged_at():
    text = HARVEST.read_text(encoding="utf-8-sig")
    start = text.index("function Test-HarvestRecentLessonDedup")
    chunk = text[start:start + 1800]
    assert "state,mergedAt" in chunk
    assert "Test-HarvestPrClosedUnmerged" in chunk
