"""Hostile pins for MRB #4209 / FR #4207: plural process-loops and already-in bobiverse-job-mrb."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    env = dict(**{k: v for k, v in __import__("os").environ.items() if k != "BOB_OUTBOX"})
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            "-Repo",
            "SimonBarnett/bobiverse",
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
        env=env,
    )


def test_mrb4209_skips_plural_process_loops_with_fail_supersede(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "FAIL-supersede: process loops already covered; closed twin tip",
        "-Lesson",
        "FAIL-supersede process loops; close as not planned",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout
    assert "FR #4207" in HARVEST.read_text(encoding="utf-8-sig")


def test_mrb4209_skips_already_in_bobiverse_job_mrb(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "MRB FAIL-superseded: tip already in bobiverse-job-mrb",
        "-Lesson",
        "FAIL-supersede citing skill-book PR",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout