"""FR #9035: Sync compose parse-gates Invoke-BobFleet; prefer bob\\tray mirror."""
from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

from repo_layout import ROOT

SYNC = ROOT / "scripts" / "Sync-BobiverseFromRepo.ps1"
# common/tests -> parents[1]=common, parents[2]=repo root for split layout
COMMON = Path(__file__).resolve().parents[1]
SYNC_ALT = COMMON / "scripts" / "Sync-BobiverseFromRepo.ps1"
FLEET_REPO = ROOT / "tray" / "src" / "Private" / "Invoke-BobFleet.ps1"


def _sync_path() -> Path:
    if SYNC.is_file():
        return SYNC
    if SYNC_ALT.is_file():
        return SYNC_ALT
    # install-style: common/scripts next to bob/
    p = Path(__file__).resolve().parents[2] / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
    assert p.is_file(), p
    return p


def test_fr9035_sync_prefers_bob_tray_src_mirror():
    text = _sync_path().read_text(encoding="utf-8")
    assert "FR #9035" in text
    assert r"bob\tray\src" in text or "bob\\tray\\src" in text
    assert "Assert-BobiverseInvokeBobFleetParses" in text or "sync-fleet-parse-gate" in text
    assert "param([string])" in text  # gate looks for nameless form


def test_fr9035_repo_fleet_still_has_dollar_names():
    text = FLEET_REPO.read_text(encoding="utf-8-sig")
    assert "param([string]$Body)" in text
    assert "param([string])" not in text


def test_fr9035_assert_refuses_nameless_param(tmp_path: Path):
    ps = shutil.which("powershell") or shutil.which("pwsh")
    assert ps
    install = tmp_path / "install"
    fleet = install / "src" / "Private" / "Invoke-BobFleet.ps1"
    fleet.parent.mkdir(parents=True)
    fleet.write_text(
        textwrap.dedent(
            """
            function Bad {
                param([string])
                return $false
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    common = Path(__file__).resolve().parents[1] / "scripts" / "Bobiverse-Common.ps1"
    if not common.is_file():
        common = Path(__file__).resolve().parents[2] / "common" / "scripts" / "Bobiverse-Common.ps1"
    assert common.is_file(), common
    script = (
        f". '{common}' ; "
        f"$r = Assert-BobiverseInvokeBobFleetParses -InstallRoot '{install}' ; "
        "if ($r.Ok) { 'OK_BAD'; exit 2 } ; "
        "Write-Output $r.Reason ; "
        "if ($r.Reason -notmatch 'nameless|parse|FR #9035') { exit 3 } ; "
        "exit 0"
    )
    r = subprocess.run(
        [ps, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr


def test_fr9035_assert_ok_on_good_fleet(tmp_path: Path):
    ps = shutil.which("powershell") or shutil.which("pwsh")
    assert ps
    install = tmp_path / "install"
    fleet = install / "src" / "Private" / "Invoke-BobFleet.ps1"
    fleet.parent.mkdir(parents=True)
    shutil.copy2(FLEET_REPO, fleet)
    common = Path(__file__).resolve().parents[1] / "scripts" / "Bobiverse-Common.ps1"
    if not common.is_file():
        common = Path(__file__).resolve().parents[2] / "common" / "scripts" / "Bobiverse-Common.ps1"
    script = (
        f". '{common}' ; "
        f"$r = Assert-BobiverseInvokeBobFleetParses -InstallRoot '{install}' ; "
        "if (-not $r.Ok) { Write-Output $r.Reason; exit 2 } ; "
        "exit 0"
    )
    r = subprocess.run(
        [ps, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
