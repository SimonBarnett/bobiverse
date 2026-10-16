"""FR #4419: Protect-HarvestBodyClosesKeywords must live on harvest tip body path; Sync Match requires it."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
    HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
if not COMMON.is_file():
    COMMON = ROOT / "scripts" / "Bobiverse-Common.ps1"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )


def test_harvest_script_has_protect_and_fr4419_markers():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "Protect-HarvestBodyClosesKeywords" in text
    assert "$body = Protect-HarvestBodyClosesKeywords $body" in text or (
        "Protect-HarvestBodyClosesKeywords $body" in text
    )
    assert "FR #4419" in text or "FR #4371" in text
    # slash-form Closes #N/#M must be handled
    assert r"#\d+(?:/#\d+)+" in text or "Closes #N/#M" in text or "/#\\d+" in text


def test_sync_harvest_match_requires_protect():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in text
    assert "Protect-HarvestBodyClosesKeywords" in text
    assert "FR #4419" in text


def test_protect_neutralizes_slash_form_closes_in_queued_body(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "FR #4419: Protect must rewrite session summary Closes #1238/#2451 before tip open",
        "-Lesson",
        "Invoke-BobiverseHarvest Protect-HarvestBodyClosesKeywords strips Closes #N/#M (FR #4419).",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
    files = list((tmp_path / "harvest-outbox").glob("*.json"))
    assert files, r.stdout + r.stderr
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    body = payload.get("body") or ""
    assert not re.search(r"(?i)\b(Closes|Fixes)\s+#\d+", body), body
    assert not re.search(r"(?i)\b(Closes|Fixes)\s+#\d+/#\d+", body), body
    assert "1238" in body and "2451" in body
    assert "closing-keyword" in body
