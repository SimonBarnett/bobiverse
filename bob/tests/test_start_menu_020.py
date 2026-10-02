"""Start Menu inventory (t761u): ONE all-users 'Bobiverse' folder with every shortcut, legacy duplicates removed,
every shortcut on the systray icon."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
SCRIPTS = ROOT / "scripts"
ICO = ROOT / "third_party" / "bob-tray" / "assets" / "bob-systray.ico"
WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")

# t794u: ONE Start Menu entry, "Start Systray" (bob). jeeves / airc contribute nothing but the transient logon helper.
EXPECTED = {
    "bob": {"Start Systray", "Complete bobiverse service logon (bob)"},
    "jeeves": set(),
    "airc": set(),
}


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8-sig")


def test_all_installers_use_the_single_folder_helper_and_no_per_user_folder():
    for n in ("Install-Bob.ps1", "Install-Jeeves.ps1", "Install-Airc.ps1"):
        assert "Install-BobiverseStartMenu" in _read(n), n
    assert "Programs\\Bobiverse" not in _read("Install-Bob.ps1")      # was the per-user scattered folder
    assert "'Bobiverse Tray.lnk')" in _read("Install-Bob.ps1")         # Desktop/Startup autostart links stay


def test_pack_ships_the_systray_icon_for_every_product():
    assert ICO.is_file() and ICO.stat().st_size > 100
    pack = _read("Pack-BobiverseRelease.ps1")
    assert "bob-systray.ico" in pack and "Stage-Product" in pack
    # the copy sits in Stage-Product (all products), not only inside the bob-only tray block
    assert pack.index("$trayIcoSrc") < pack.index("Copy-Item (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\\nssm")


def test_restart_service_script_never_touches_ergo():
    t = _read("Restart-BobService.ps1")
    assert "ValidateSet('ircJeeves', 'ircBob', 'Airc')" in t and "BobIrcd'" not in t.split("ValidateSet")[1].split("]")[0]


HARNESS = r'''
. "{common}"
$ErrorActionPreference = 'Stop'
$base = "{base}"
$all = Join-Path $base 'ProgramData\Programs'
$user = Join-Path $base 'Users\Alice\Programs'
foreach ($d in @($all, $user, (Join-Path $user 'Bobiverse'), (Join-Path $user 'Startup'), (Join-Path $all 'Bob Systray'))) {{ New-Item -ItemType Directory -Force -Path $d | Out-Null }}
function New-Dummy($p) {{ $w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut($p); $s.TargetPath = 'notepad.exe'; $s.Save() }}
New-Dummy (Join-Path $all 'Bob Systray.lnk'); New-Dummy (Join-Path $all 'Bobiverse Tray.lnk'); New-Dummy (Join-Path $all 'Restart ircBob.lnk')
New-Dummy (Join-Path $all 'Bob Systray\Bob Systray.lnk')
New-Dummy (Join-Path $user 'Bob Systray (2).lnk'); New-Dummy (Join-Path $user 'Bobiverse\Bob Services.lnk'); New-Dummy (Join-Path $user 'Bobiverse\Bobiverse Tray.lnk')
New-Dummy (Join-Path $user 'Startup\Bobiverse Tray.lnk'); New-Dummy (Join-Path $all 'Notepad Unrelated.lnk')
$smd = Get-BobiverseStartMenuDir -ProgramsRoot $all
New-Item -ItemType Directory -Force -Path $smd | Out-Null
foreach ($n in 'Bob Services', 'Restart ircBob', 'Restart Airc', 'Jeeves command reference', 'Logs (bob)', 'Skill books (jeeves)', 'Agent guide (airc)', 'Bobiverse Tray') {{ New-Dummy (Join-Path $smd ($n + '.lnk')) }}
foreach ($prod in 'bob', 'jeeves', 'airc') {{
    $ir = Join-Path $base "ai\$prod"
    New-Item -ItemType Directory -Force -Path (Join-Path $ir 'assets'), (Join-Path $ir 'scripts'), (Join-Path $ir 'logs'), (Join-Path $ir '.grok\skills') | Out-Null
    Copy-Item "{ico}" (Join-Path $ir 'assets\bob-systray.ico') -Force
    Set-Content (Join-Path $ir 'AGENTS.md') 'x'
    $p = @{{ Product = $prod; InstallRoot = $ir; MachineId = 'testbox'; StartMenuDir = $smd; ProgramsRoots = @($all, $user) }}
    if ($prod -eq 'bob') {{ $p.NeedLogon = $true; $p.IncludeTray = $true }}
    [void](Install-BobiverseStartMenu @p)
}}
# second run = idempotent / upgrade
[void](Install-BobiverseStartMenu -Product bob -InstallRoot (Join-Path $base 'ai\bob') -MachineId testbox -IncludeTray -StartMenuDir $smd -ProgramsRoots @($all, $user))
$w = New-Object -ComObject WScript.Shell
$out = [ordered]@{{}}
$out.folders = @(Get-ChildItem $all -Directory | % Name)
$out.top = @(Get-ChildItem $all -File -Filter *.lnk | % Name)
$out.userTop = @(Get-ChildItem $user -File -Filter *.lnk -ErrorAction SilentlyContinue | % Name)
$out.userFolders = @(Get-ChildItem $user -Directory | % Name)
$out.startup = @(Get-ChildItem (Join-Path $user 'Startup') -File | % Name)
$out.shortcuts = @(Get-ChildItem $smd -File -Filter *.lnk | % {{ $s = $w.CreateShortcut($_.FullName); [ordered]@{{ name = $_.BaseName; icon = $s.IconLocation; target = $s.TargetPath }} }})
$out | ConvertTo-Json -Depth 5 -Compress | Set-Content "{res}" -Encoding UTF8
'''


@WIN
def test_install_creates_one_folder_dedupes_legacy_and_uses_the_tray_icon(tmp_path):
    res = tmp_path / "out.json"
    ps1 = tmp_path / "h.ps1"
    ps1.write_text(HARNESS.format(common=SCRIPTS / "Bobiverse-Common.ps1", base=tmp_path, ico=ICO, res=res), encoding="utf-8-sig")
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    out = json.loads(res.read_text(encoding="utf-8-sig"))
    assert out["folders"] == ["Bobiverse"]                       # 'Bob Systray' folder gone, only the one folder
    assert out["top"] == ["Notepad Unrelated.lnk"]               # no Bob/Bobiverse top-level duplicates; unrelated kept
    assert out["userTop"] == [] and out["userFolders"] == ["Startup"]     # per-user dupes + per-user Bobiverse folder gone
    assert out["startup"] == ["Bobiverse Tray.lnk"]              # tray autostart untouched
    names = {s["name"] for s in out["shortcuts"]}
    # after the idempotent bob re-run (no NeedLogon) the logon helper is removed; all other products remain
    assert names == {"Start Systray"}                           # the older per-product links inside the folder were pruned too
    assert len([s for s in out["shortcuts"] if s["name"] == "Start Systray"]) == 1
    for s in out["shortcuts"]:
        assert s["icon"].lower().endswith("bob-systray.ico,0"), s    # every shortcut on the systray icon
    tray = [s for s in out["shortcuts"] if s["name"] == "Start Systray"][0]
    assert tray["target"].lower().endswith("powershell.exe")


@WIN
def test_spec_inventory_per_product(tmp_path):
    ps1 = tmp_path / "s.ps1"
    ps1.write_text('. "%s"\nforeach ($p in "bob","jeeves","airc") { $s = Get-BobiverseShortcutSpec -Product $p -InstallRoot "C:\\ai\\$p" -MachineId m -NeedLogon -IncludeTray -Icon "C:\\x\\bob-systray.ico"; "$p=" + (($s | %% Name) -join "|") }\n'
                   % (SCRIPTS / "Bobiverse-Common.ps1"), encoding="utf-8-sig")
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    got = {ln.split("=")[0]: set(ln.split("=", 1)[1].split("|")) for ln in run.stdout.splitlines() if "=" in ln}
    assert got == {"bob": EXPECTED["bob"], "jeeves": {"Complete bobiverse service logon (jeeves)"},
                   "airc": {"Complete bobiverse service logon (airc)"}}


@WIN
def test_start_systray_is_the_only_entry_and_launches_the_tray_launcher(tmp_path):
    ps1 = tmp_path / "s.ps1"
    ps1.write_text('. "%s"\n$s = @(Get-BobiverseShortcutSpec -Product bob -InstallRoot "C:\\ai\\bob" -MachineId m -IncludeTray -Icon "C:\\x\\bob-systray.ico"); $s | ConvertTo-Json -Compress\n'
                   % (SCRIPTS / "Bobiverse-Common.ps1"), encoding="utf-8-sig")
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    spec = json.loads(run.stdout)
    spec = spec if isinstance(spec, list) else [spec]
    assert [s["Name"] for s in spec] == ["Start Systray"]
    assert "Start-BobTray.ps1" in spec[0]["Arguments"] and "-ForceNew" in spec[0]["Arguments"]
    assert spec[0]["Icon"].endswith("bob-systray.ico,0")

