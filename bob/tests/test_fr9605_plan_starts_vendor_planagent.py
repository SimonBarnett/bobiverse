# -*- coding: utf-8 -*-
"""FR #9605: TipForm / Watch Plan start vendor\\plan\\PlanAgent.exe (not plan\\)."""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
EVIDENCE = REPO / "bob" / "docs" / "fr-8693-plan-exe-evidence.md"
BOB49 = REPO / "bob" / "docs" / "bob-49-bob-ear-msi-include-plan-evidence.md"


def test_fr9605_tipform_starts_vendor_planagent():
    cs = TRAY.read_text(encoding="utf-8-sig")
    body = cs.split("void StartPlanExe()", 1)[1].split("void StartWorker(", 1)[0]
    assert '"vendor", "plan", "PlanAgent.exe"' in body
    assert 'Path.Combine(root, "plan", "PlanAgent.exe")' not in body
    assert "bob-plan.exe" not in body
    assert "Plan - missing exe" in body
    assert "start exe missing" in body
    # FR #9661: --root <install>\plan (exe stays under vendor\plan)
    assert "planRoot.Replace" in body and '--root' in body


def test_fr9605_watch_starts_vendor_planagent():
    ps = WATCH.read_text(encoding="utf-8-sig")
    fn = ps.split("function Start-BobTrayPlanExe {", 1)[1].split("function Start-BobTrayWorkerExe {", 1)[0]
    assert "vendor\\plan\\PlanAgent.exe" in fn
    assert "Join-Path $RepoRoot 'plan\\PlanAgent.exe'" not in fn
    assert "bob-plan.exe" not in fn
    assert "Plan - missing exe" in fn
    # FR #9661
    assert "ArgumentList @('--root', $planRoot)" in fn


def test_fr9605_docs_pin_vendor_path():
    ev = EVIDENCE.read_text(encoding="utf-8")
    assert "vendor\\plan\\PlanAgent.exe" in ev or "vendor/plan/PlanAgent.exe" in ev
    assert "9605" in ev
    bob49 = BOB49.read_text(encoding="utf-8")
    assert "vendor/plan/PlanAgent.exe" in bob49.replace("\\", "/")
    assert "TipForm Plan clicks start" in bob49
    assert "vendor\\plan\\PlanAgent.exe" in bob49 or "vendor/plan/PlanAgent.exe" in bob49
