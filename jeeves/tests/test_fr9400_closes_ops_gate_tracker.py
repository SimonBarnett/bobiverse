# -*- coding: utf-8 -*-
"""FR #9400: never Closes ops/gate trackers while Depends-on / GateIssues OPEN."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))
import closes_ops_gate_tracker as chk  # noqa: E402

FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
MONITOR = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
TOOL = ROOT / "common" / "scripts" / "closes_ops_gate_tracker.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr9400_detects_gateissues_and_depends():
    body = (
        "## Status\nOps install NOT done.\n\n"
        "Depends-on: SimonBarnett/skills-visionary#155\n\n"
        "## GateIssues\n- skills-visionary#155\n"
    )
    assert chk.issue_has_open_gate_markers(body)
    assert not chk.issue_has_open_gate_markers("Depends-on: (none)\n\nDone.")


def test_fr9400_closes_blocked_when_gates_open():
    pr = "Closes SimonBarnett/bobiverse#9376\n\nTool only.\n"
    issue = (
        "CAST IRON: Do not Closes while GateIssues OPEN.\n"
        "Depends-on: #155\n## GateIssues\n- #155\n"
    )
    errs = chk.check_pr_against_issues(pr, {9376: issue})
    assert errs
    assert any("9400" in e and "9376" in e for e in errs)


def test_fr9400_refs_ok_and_closes_clean_issue_ok():
    pr_refs = "Refs SimonBarnett/bobiverse#9376\n\nTool landed.\n"
    issue = "Depends-on: #155\n## GateIssues\n- #155\n"
    assert chk.check_pr_against_issues(pr_refs, {9376: issue}) == []
    pr_ok = "Closes SimonBarnett/bobiverse#9400\n"
    assert (
        chk.check_pr_against_issues(
            pr_ok, {9400: "Simple FR.\nDepends-on: (none)\n"}
        )
        == []
    )


def test_fr9400_stamp_cli(tmp_path: Path):
    stamp = {
        "pr_body": "Closes #9376\n",
        "issues": {
            "9376": {
                "body": "Ops install NOT done.\nDepends-on: #155\n## GateIssues\n"
            }
        },
    }
    path = tmp_path / "stamp.json"
    path.write_text(json.dumps(stamp), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(TOOL), str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_fr9400_skills_cast_iron():
    fr = FR.read_text(encoding="utf-8")
    mon = MONITOR.read_text(encoding="utf-8")
    _no_bom(FR)
    _no_bom(MONITOR)
    assert "9400" in fr and "9400" in mon
    assert "GateIssues" in fr or "gate tracker" in fr.lower()
    low_fr = fr.lower()
    assert "refs" in low_fr and "closes" in low_fr
    assert "ops" in low_fr or "gate" in low_fr
    low_m = mon.lower()
    assert "refs" in low_m or "toward" in low_m
    assert "closes" in low_m
    assert "gateissues" in low_m or "gate issues" in low_m or "depends-on" in low_m
