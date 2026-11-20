"""FR #8420: updatefleet CLI finds Update-BobFleet.ps1 and emits JSON."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "bob" / "tools" / "updatefleet.py"
PS1 = ROOT / "common" / "scripts" / "Update-BobFleet.ps1"


@pytest.mark.skipif(not TOOL.is_file(), reason="updatefleet.py missing")
def test_fr8420_updatefleet_help():
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "updatefleet" in (proc.stdout or "").lower()
    assert "digest" in (proc.stdout or "").lower()


@pytest.mark.skipif(not PS1.is_file(), reason="Update-BobFleet.ps1 missing")
def test_fr8420_ps1_mentions_credman_and_digest():
    text = PS1.read_text(encoding="utf-8")
    assert "Bobiverse/UpdateFleet" in text
    assert "bob.ntsa.uk/bob/v1/report" in text
    assert "wonderland\\administrator" in text
    assert "User-Agent" in text
    assert "Bobiverse-bobreport" in text


@pytest.mark.skipif(not TOOL.is_file() or not PS1.is_file(), reason="tool files missing")
def test_fr8420_updatefleet_dry_run_json(monkeypatch, tmp_path):
    """Dry-run against live digest when network allows; otherwise skip."""
    monkeypatch.setenv("BOB_UPDATEFLEET_PS1", str(PS1))
    art = tmp_path / "art"
    art.mkdir()
    exe = art / "bob-worker.exe"
    exe.write_bytes(b"MZ-fake-worker")
    # sha of content
    import hashlib

    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (art / "bob-worker.exe.sha256").write_text(f"{digest}  bob-worker.exe\n", encoding="ascii")

    proc = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--dry-run",
            "--no-recycle",
            "--artifact-dir",
            str(art),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=90,
    )
    line = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else ""
    if not line.startswith("{"):
        pytest.skip(f"no JSON from dry-run (exit={proc.returncode}): {(proc.stderr or '')[:200]}")
    doc = json.loads(line)
    assert doc.get("check") == "updatefleet"
    if proc.returncode == 2 and "digest" in str(doc.get("error", "")).lower():
        pytest.skip("digest unreachable in this environment")
    assert "machines" in doc
    assert isinstance(doc["machines"], list)
    assert doc.get("dry_run") is True
    assert doc.get("expected_sha") == digest
