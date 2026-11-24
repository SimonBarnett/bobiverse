# -*- coding: utf-8 -*-
"""FR #9661: TipForm/Watch PlanAgent start passes --root <install>\\plan."""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
EVIDENCE = REPO / "bob" / "docs" / "fr-8693-plan-exe-evidence.md"


def test_fr9661_tipform_passes_root_and_guards_agents():
    cs = TRAY.read_text(encoding="utf-8-sig")
    body = cs.split("void StartPlanExe()", 1)[1].split("void StartWorker(", 1)[0]
    assert 'Path.Combine(root, "plan")' in body
    assert 'Path.Combine(planRoot, "AGENTS.md")' in body
    assert 'psi.Arguments = "--root "" + planRoot.Replace' in body
    assert 'EnvironmentVariables["PLAN_AGENT_ROOT"]' in body
    assert "Plan - missing AGENTS.md" in body
    assert "start plan root missing" in body
    assert '"vendor", "plan", "PlanAgent.exe"' in body


def test_fr9661_watch_passes_root_and_guards_agents():
    ps = WATCH.read_text(encoding="utf-8-sig")
    fn = ps.split("function Start-BobTrayPlanExe {", 1)[1].split("function Start-BobTrayWorkerExe {", 1)[0]
    assert "Join-Path $RepoRoot 'plan'" in fn
    assert "Join-Path $planRoot 'AGENTS.md'" in fn
    assert "ArgumentList @('--root', $planRoot)" in fn
    assert "$env:PLAN_AGENT_ROOT = $planRoot" in fn
    assert "Plan - missing AGENTS.md" in fn
    assert "vendor\\plan\\PlanAgent.exe" in fn
    # FR #2585: no quoted --root value baked into ArgumentList entries
    assert "@('--root', \"`$planRoot\")" not in fn
    assert '@("--root", "`"$planRoot`"")' not in fn


def test_fr9661_evidence_cites_root():
    ev = EVIDENCE.read_text(encoding="utf-8")
    assert "9661" in ev
    assert "--root" in ev
    assert "plan\\AGENTS.md" in ev or "plan/AGENTS.md" in ev
