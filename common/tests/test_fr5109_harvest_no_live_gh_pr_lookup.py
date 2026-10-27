"""FR #5109: product-MSI harvest pytest must not depend on live gh pr view."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def test_fr5109_script_has_no_gh_pr_lookup_gate():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "BOBIVERSE_HARVEST_NO_GH_PR_LOOKUP" in text
    assert "FR #5109" in text


def test_fr5109_product_msi_queues_when_lookup_disabled(tmp_path: Path, monkeypatch):
    """Same 2991 product lesson + live harvest-lesson #2988 citation still queues when lookup is off."""
    monkeypatch.setenv("BOBIVERSE_HARVEST_NO_GH_PR_LOOKUP", "1")
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            "-Summary",
            "Earlier MRB #2988 FAIL-superseded a twin; this tip is product MSI SkipCopy",
            "-Lesson",
            "MSI RunInstall: when -MsiProductVersion is set, SkipCopy so heat-laid scripts win",
            "-OutboxDir",
            str(tmp_path / "harvest-outbox"),
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
        env=os.environ.copy(),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson/pin job" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
