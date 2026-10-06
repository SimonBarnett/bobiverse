"""Systray requirements (t794u-t800u): Status default item, Acknowledge About dialog (logo, version, every install folder),
Exit ordering + detached service stop, Start restarts the service, no update logic in the tray, systray icon for the worker."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "third_party" / "bob-tray"
TOOLS = TRAY / "tools"
SCRIPTS = ROOT / "scripts"
COMMON = SCRIPTS / "Bobiverse-Common.ps1"
WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _ps(tmp_path: Path, body: str, timeout: int = 90):
    f = tmp_path / "t.ps1"
    f.write_text(body, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(f)],
                       capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _fn(text: str, name: str) -> str:
    """Body of top-level `function <name> {` ... up to the next top-level function / statement at column 0."""
    m = re.search(r"^function %s\b.*?(?=^(?:function |\$|#|foreach |if |\[)|\Z)" % re.escape(name), text, re.S | re.M)
    assert m, name
    return m.group(0)


WATCH = _t(TOOLS / "Watch-BobTray.ps1")


# ------------------------------------------------------------------------------------------------ 1. Status = default item
def test_status_is_the_bold_default_item_run_by_menu_left_click_and_double_click():
    assert "$miStatus.Font = New-Object System.Drawing.Font($miStatus.Font, [System.Drawing.FontStyle]::Bold)" in WATCH
    assert "$miStatus.Add_Click({ Invoke-BobTrayStatus })" in WATCH
    body = _fn(WATCH, "Invoke-BobTrayStatus")
    assert "Update-Hover" in body and "Show-BobTrayCard -Reason 'click'" in body       # the pools dialog
    click = WATCH[WATCH.index("$notify.Add_MouseClick({"):]
    left = click[:click.index("$notify.Add_MouseDoubleClick")]
    dbl = click[click.index("$notify.Add_MouseDoubleClick"):click.index("$flash = ")]
    assert "Invoke-BobTrayStatus" in left and "MouseButtons]::Left" in left
    assert "Invoke-BobTrayStatus" in dbl and "MouseButtons]::Left" in dbl


# ------------------------------------------------------------------------------------------------ 2. Acknowledge dialog
def test_acknowledge_clears_the_alert_and_shows_the_about_dialog_with_logo_and_credit():
    m = re.search(r"\$miAck\.Add_Click\(\{(.*?)\}\)", WATCH, re.S)
    assert m and m.group(1).index("Clear-Attention") < m.group(1).index("Show-BobTrayAbout")
    about = _fn(WATCH, "Show-BobTrayAbout")
    assert "by Simon Barnett" in about and "Get-BobTrayLogoImage" in about
    assert "Get-BobInstallInfo" in about and "Format-BobInstallInfo" in about and "Get-BobTrayProductVersionLabel" in about
    logo = _fn(WATCH, "Get-BobTrayLogoImage")
    assert "assets\\ntsa-gut-logo.png" in WATCH and "ReadAllBytes($script:ntsaGutLogoPath)" in logo


def test_ntsa_logo_asset_is_a_real_png_referenced_everywhere_and_no_placeholder_remains():
    logo = TRAY / "assets" / "ntsa-gut-logo.png"
    data = logo.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 1000
    w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    assert w == h and 64 <= w <= 256
    assert not (TRAY / "assets" / "ntsa-gut-logo-PLACEHOLDER.png").exists()
    for f in (TOOLS / "Watch-BobTray.ps1", SCRIPTS / "Sync-BobTrayFromAgenticBuild.ps1"):
        assert "PLACEHOLDER" not in _t(f).upper(), f.name
    pack = ROOT.parent / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
    if pack.is_file():
        assert "foreach ($sub in @('tools', 'assets'))" in _t(pack)
    assert "ntsa-gut-logo.png" in _t(SCRIPTS / "Sync-BobTrayFromAgenticBuild.ps1")
    repo_sync = ROOT.parent / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
    if repo_sync.is_file():
        assert "third_party\\bob-tray\\assets" in _t(repo_sync)


# ------------------------------------------------------------------------------------------------ 3. install inventory
INFO_HARNESS = r'''
. "{info}"
$ErrorActionPreference = 'Stop'
$base = "{base}"
function Mk($root, $prod, $ver, [switch]$Ergo) {{
    $d = Join-Path $root $prod
    New-Item -ItemType Directory -Force -Path (Join-Path $d 'scripts') | Out-Null
    if ($Ergo) {{ Set-Content (Join-Path $d 'ergo.exe') 'x' }} else {{ Set-Content (Join-Path $d 'VERSION') $ver }}
    return $d
}}
$git = {{ param($d, $a) if ($a[0] -eq 'rev-parse') {{ 'abc1234' }} else {{ '2026-10-02T12:14:00+00:00' }} }}
function Svc($n, $dir) {{ [pscustomobject]@{{ Name = $n; State = 'Running'; Dir = $dir }} }}
$out = [ordered]@{{}}
function Run($key, $roots, $svcs) {{
    $probe = {{ param($names) $svcs }}.GetNewClosure()
    $rows = @(Get-BobInstallInfo -AiRoots $roots -ServiceProbe $probe -GitProbe $git)
    $script:out[$key] = @($rows | ForEach-Object {{ [ordered]@{{ product = $_.Product; path = $_.Path.Replace($base, ''); version = $_.Version; released = $_.Released; src = $_.ReleasedSource; commit = $_.Commit; service = $_.Service; state = $_.ServiceState }} }})
}}
# 1: bob only (no jeeves / airc / ergo at all)
$a1 = Join-Path $base 'a1'; $b1 = Mk $a1 'bob' '0.1.19'
Run 'bob_only' @($a1) @((Svc 'ircBob' $b1))
# 2: bob + airc
$a2 = Join-Path $base 'a2'; $b2 = Mk $a2 'bob' '0.1.19'; $c2 = Mk $a2 'airc' '0.1.18'
Run 'bob_airc' @($a2) @((Svc 'ircBob' $b2), (Svc 'Airc' $c2))
# 3: bob + jeeves + airc
$a3 = Join-Path $base 'a3'; $b3 = Mk $a3 'bob' '0.1.19'; $j3 = Mk $a3 'jeeves' '0.1.17'; $c3 = Mk $a3 'airc' '0.1.18'
Run 'all_three' @($a3) @((Svc 'ircBob' $b3), (Svc 'ircJeeves' $j3), (Svc 'Airc' $c3))
# 4: ergo too, found by the ai-root scan only (no service)
$e4 = Mk $a3 'ergo' '' -Ergo
Run 'with_ergo' @($a3) @()
# 5: the same product in two ai roots = two rows; an unrelated empty root is ignored
$a5 = Join-Path $base 'a5'; [void](Mk $a5 'bob' '0.1.20'); New-Item -ItemType Directory -Force -Path (Join-Path $base 'empty\ai') | Out-Null
Run 'two_roots' @($a1, $a5, (Join-Path $base 'empty\ai'), (Join-Path $base 'missing')) @()
# 6: a service whose folder is unknown / gone still lists, without error
Run 'service_only' @() @((Svc 'ircJeeves' ''))
# 7: nothing at all
Run 'nothing' @((Join-Path $base 'nope')) @()
# 8: BUILD.json beats git
Set-Content (Join-Path $b1 'BUILD.json') '{{"product":"bob","version":"0.1.19","built_utc":"2026-09-30T08:00:00Z","commit":"deadbee"}}'
Run 'build_json' @($a1) @()
$text = Format-BobInstallInfo -Rows @(Get-BobInstallInfo -AiRoots @($a3) -ServiceProbe {{ param($n) @((Svc 'ircBob' $b3)) }} -GitProbe $git)
$out['text'] = $text
$out['empty_text'] = Format-BobInstallInfo -Rows @()
$out | ConvertTo-Json -Depth 6 -Compress | Set-Content "{res}" -Encoding UTF8
'''


@pytest.fixture()
def info(tmp_path):
    if sys.platform != "win32":
        pytest.skip("needs Windows PowerShell")
    res = tmp_path / "o.json"
    _ps(tmp_path, INFO_HARNESS.format(info=TOOLS / "Get-BobInstallInfo.ps1", base=str(tmp_path) + "\\", res=res))
    return json.loads(res.read_text(encoding="utf-8-sig"))


def _prods(rows):
    return [r["product"] for r in rows] if isinstance(rows, list) else [rows["product"]]


def _rows(x):
    return x if isinstance(x, list) else [x]


@WIN
def test_about_lists_only_bob_when_only_bob_is_installed(info):
    rows = _rows(info["bob_only"])
    assert _prods(rows) == ["bob"]
    r = rows[0]
    assert (r["version"], r["commit"], r["path"], r["service"], r["state"]) == ("0.1.19", "abc1234", "a1\\bob", "ircBob", "Running")
    assert r["released"] == "2026-10-02 12:14 UTC" and r["src"] == "commit"


@WIN
def test_about_lists_bob_and_airc_and_nothing_for_the_missing_jeeves_and_ergo(info):
    rows = _rows(info["bob_airc"])
    assert _prods(rows) == ["bob", "airc"]
    assert {r["product"]: r["version"] for r in rows} == {"bob": "0.1.19", "airc": "0.1.18"}
    assert {r["product"]: r["service"] for r in rows} == {"bob": "ircBob", "airc": "Airc"}


@WIN
def test_about_lists_bob_jeeves_airc_each_with_version_date_commit_and_path(info):
    rows = _rows(info["all_three"])
    assert _prods(rows) == ["bob", "jeeves", "airc"]
    for r in rows:
        assert r["version"] != "-" and r["released"] != "-" and r["commit"] == "abc1234" and r["path"].startswith("a3\\")
    assert {r["product"]: r["version"] for r in rows} == {"bob": "0.1.19", "jeeves": "0.1.17", "airc": "0.1.18"}


@WIN
def test_about_finds_ergo_by_the_ai_root_scan_and_every_folder_when_a_product_is_in_two_roots(info):
    assert _prods(_rows(info["with_ergo"]))[-1] == "ergo"
    two = _rows(info["two_roots"])
    assert _prods(two) == ["bob", "bob"] and [r["path"] for r in two] == ["a1\\bob", "a5\\bob"]


@WIN
def test_about_never_errors_on_missing_products_and_a_service_without_a_folder_still_lists(info):
    assert _rows(info["nothing"]) == [] or info["nothing"] in ([], None)
    s = _rows(info["service_only"])
    assert _prods(s) == ["jeeves"] and s[0]["path"] == "(unknown)" and s[0]["service"] == "ircJeeves"
    assert "No Bobiverse products" in info["empty_text"]


@WIN
def test_about_prefers_build_json_for_release_date_and_commit(info):
    r = _rows(info["build_json"])[0]
    assert r["released"] == "2026-09-30 08:00 UTC" and r["src"] == "built" and r["commit"] == "deadbee"


@WIN
def test_about_text_has_every_field(info):
    text = info["text"]
    for needle in ("bob  0.1.19", "jeeves  0.1.17", "airc  0.1.18", "released:", "commit:   abc1234", "path:", "service:"):
        assert needle in text, needle


def test_pack_writes_build_json_and_tray_ships_the_about_helpers():
    pack = _t(ROOT.parent / "common" / "scripts" / "Pack-BobiverseRelease.ps1") if (ROOT.parent / "common").is_dir() else ""
    if pack:
        assert "BUILD.json" in pack and "built_utc" in pack
    for f in ("Get-BobInstallInfo.ps1", "BobTrayLifecycle.ps1", "Invoke-BobTrayServiceControl.ps1", "BobTrayStartWorker.ps1"):
        assert (TOOLS / f).is_file()
        assert f in _t(SCRIPTS / "Sync-BobTrayFromAgenticBuild.ps1")      # preserved across a vendor re-sync


# ------------------------------------------------------------------------------------------------ 4. Exit ordering (t798u)
@WIN
def test_exit_sequence_runs_dialogs_then_icon_then_ui_then_stop_even_if_a_step_fails(tmp_path):
    out = _ps(tmp_path, r'''
. "%s"
$global:trace = New-Object System.Collections.Generic.List[string]
$r = Invoke-BobTrayExitSequence -CloseDialogs { $global:trace.Add('dialogs') } -DisposeIcon { $global:trace.Add('icon'); throw 'boom' } `
    -ExitUi { $global:trace.Add('ui') } -StopService { $global:trace.Add('stop') }
"RAN=" + ($r -join ',')
"TRACE=" + ($global:trace -join ',')
''' % (TOOLS / "BobTrayLifecycle.ps1"))
    assert "RAN=close-dialogs,dispose-icon,exit-ui,stop-service" in out
    assert "TRACE=dialogs,icon,ui,stop" in out


def test_tray_exit_handler_closes_then_exits_then_stops_without_waiting():
    ex = _fn(WATCH, "Invoke-BobTrayExit")
    order = [ex.index(k) for k in ("-CloseDialogs", "-DisposeIcon", "-ExitUi", "-StopService")]
    assert order == sorted(order)
    assert "Close-BobTrayDialogs" in ex and "$notify.Dispose()" in ex and "$ctx.ExitThread()" in ex and "Stop-BobTrayService" in ex
    for slow in ("Request-BobTrayIrcLogout", "Wait-", "WaitForExit", "Start-Sleep", "Stop-BobiverseMoot", "-Wait"):
        assert slow not in ex, slow                                       # nothing slow before/around the exit
    assert "$miExit.Add_Click({ Invoke-BobTrayExit })" in WATCH
    tail = WATCH[WATCH.index("[System.Windows.Forms.Application]::Run($ctx)"):]
    assert "if ($script:trayExitReason -ne 'Exit')" in tail and tail.index("trayExitReason") < tail.index("Request-BobTrayIrcLogout")
    cd = _fn(WATCH, "Close-BobTrayDialogs")
    assert "aboutForm" in cd and "$script:tip" in cd


@WIN
def test_service_stop_is_fire_and_forget(tmp_path):
    out = _ps(tmp_path, r'''
. "%s"
$launch = { param($f, $a) $global:seen = "$f|$a"; 4242 }
"PID=" + (Stop-BobTrayService -ServiceName ircBob -Launcher $launch)
"SEEN=" + $global:seen
"BAD=" + (Stop-BobTrayService -ServiceName 'ircBob; calc' -Launcher $launch)
# a real child that runs for 6 s must not hold us up
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-BobTrayDetached -FilePath "$env:SystemRoot\System32\cmd.exe" -Arguments '/c ping -n 7 127.0.0.1 >nul'
"MS=" + $sw.ElapsedMilliseconds
"ALIVE=" + [bool](Get-Process -Id $p -ErrorAction SilentlyContinue)
Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
''' % (TOOLS / "BobTrayLifecycle.ps1"))
    assert "PID=4242" in out and re.search(r"SEEN=.*sc\.exe\|stop ircBob", out) and "BAD=0" in out
    assert int(re.search(r"MS=(\d+)", out).group(1)) < 3000 and "ALIVE=True" in out
    life = _t(TOOLS / "BobTrayLifecycle.ps1")
    assert "WaitForExit" not in life and "-Wait" not in life


# ------------------------------------------------------------------------------------------------ 5. Start restarts the service
@WIN
def test_restart_service_helper_is_detached_and_start_systray_calls_it(tmp_path):
    out = _ps(tmp_path, r'''
. "%s"
$launch = { param($f, $a) $global:seen = "$f|$a"; 777 }
"PID=" + (Restart-BobTrayService -ServiceName ircBob -ToolsDir "%s" -Launcher $launch)
"SEEN=" + $global:seen
''' % (TOOLS / "BobTrayLifecycle.ps1", TOOLS))
    assert "PID=777" in out and "powershell.exe|" in out
    assert "Invoke-BobTrayServiceControl.ps1" in out and "-Action Restart -ServiceName ircBob" in out
    fleet = _t(TOOLS / "Start-BobFleetTray.ps1")
    assert "Restart-BobTrayService" in fleet and "[switch]$SkipServiceRestart" in fleet
    # restart happens only when a tray is really being started: after the 'already running' exit and the WhatIf exit
    assert fleet.index("Bob Systray already running") < fleet.index("Restart-BobTrayService") < fleet.index("Invoke-CimMethod")
    assert "-SkipServiceRestart" in _t(ROOT.parent / "common" / "scripts" / "bob_recycle.py") if (ROOT.parent / "common").is_dir() else True


@WIN
def test_service_control_helper_dry_run_and_rejects_bad_names(tmp_path):
    h = TOOLS / "Invoke-BobTrayServiceControl.ps1"
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), "-Action", "Restart", "-ServiceName", "ircBob", "-DryRun"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "dry-run Restart ircBob" in r.stdout
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), "-ServiceName", "x; calc"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2


@WIN
def test_installer_grants_interactive_users_start_stop_on_the_service_acl(tmp_path):
    out = _ps(tmp_path, r'''
. "%s"
$cur = 'D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)'
$n = Get-BobiverseServiceSddlWithUserControl -Sddl $cur
"NEW=" + $n
"IDEM=" + ((Get-BobiverseServiceSddlWithUserControl -Sddl $n) -ceq $n)
"NOIU=" + (Get-BobiverseServiceSddlWithUserControl -Sddl 'D:(A;;GA;;;SY)S:(AU;FA;GA;;;WD)')
''' % COMMON)
    new = re.search(r"NEW=(.*)", out).group(1)
    iu = re.search(r"\(A;;([A-Z]+);;;IU\)", new).group(1)
    assert "RP" in iu and "WP" in iu and "LO" in iu and "(A;;CCLCSWRPWPDTLOCRRC;;;SY)" in new       # others untouched
    assert "IDEM=True" in out
    assert re.search(r"NOIU=D:\(A;;GA;;;SY\)\(A;;[A-Z]*RP[A-Z]*;;;IU\)S:", out)                      # ACE goes before the SACL
    assert "Grant-BobiverseServiceUserControl -Name $ServiceName" in _t(SCRIPTS / "Install-Bob.ps1")


# ------------------------------------------------------------------------------------------------ 6. no update logic in the tray
def test_tray_has_no_update_logic_and_the_update_scripts_are_gone():
    for gone in ("Update-BobSystrayFromGit.ps1", "Show-BobSystrayUpdatingDialog.ps1", "Bootstrap-BobSystray.ps1"):
        assert not (TOOLS / gone).exists(), gone
    pat = re.compile(r"Update-BobSystrayFromGit|Show-BobSystrayUpdating|Bootstrap-BobSystray|git (pull|fetch|clone)|Check-BobiverseUpdate|Update-BobiverseService|msiexec", re.I)
    # Install-VisionarySkills.ps1 only refreshes the Plan agent's visionary SKILL books (git clone/pull of a skills repo); it never updates
    # the tray or any product, so it is not tray update logic.
    for f in sorted(TOOLS.glob("*.ps1")) + [SCRIPTS / "Start-BobTray.ps1", SCRIPTS / "Start-BobTrayInteractive.ps1"]:
        if f.name == "Install-VisionarySkills.ps1":
            continue
        text = re.sub(r"(?m)^\s*#.*$", "", _t(f))        # comments may say what the tray no longer does
        assert not pat.search(text), f.name
    repo_sync = _t(ROOT.parent / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1") if (ROOT.parent / "common").is_dir() else ""
    if repo_sync:       # older installs still carry the update scripts: the work-tree sync removes them
        for gone in ("Update-BobSystrayFromGit.ps1", "Show-BobSystrayUpdatingDialog.ps1", "Bootstrap-BobSystray.ps1"):
            assert gone in repo_sync
    sync = _t(SCRIPTS / "Sync-BobTrayFromAgenticBuild.ps1")
    assert "Update-BobSystrayFromGit.ps1'" not in sync.replace("Update-BobSystrayFromGit / ", "")
    assert "-SkipUpdate" not in _t(SCRIPTS / "Start-BobTray.ps1").replace("-SkipUpdate to", "")
    # the service owns the update
    start = _t(SCRIPTS / "Start-Bob.ps1")
    assert "Update-BobiverseService.ps1" in start and "Sync" in start


# ------------------------------------------------------------------------------------------------ 7. systray icon for the worker exe + window
def test_worker_exe_is_built_with_the_systray_icon_and_the_window_uses_it():
    b = _t(SCRIPTS / "Build-BobWorker.ps1")
    # Build appends $icoArgs (icon + --add-data); splat @icoArgs was replaced by $argList += $icoArgs.
    assert "'--icon', $ico" in b and "--add-data" in b and "bob-systray.ico" in b
    assert "$icoArgs" in b and "$argList += $icoArgs" in b
    w = _t(SCRIPTS / "bob_worker.py")
    assert w.index("ensure_console(f\"Bob worker") < w.index("set_console_icon(Path(args.install_root))")
    assert "WM_SETICON" in w and "LoadImageW.argtypes" in w and "SendMessageW.argtypes" in w   # typed: 64-bit handles


def test_worker_finds_the_systray_icon_in_the_install_then_the_bundle(tmp_path, monkeypatch):
    import bob_worker as bw
    inst = tmp_path / "inst"
    (inst / "assets").mkdir(parents=True)
    (inst / "assets" / "bob-systray.ico").write_bytes(b"ico")
    assert bw.find_window_icon(inst) == inst / "assets" / "bob-systray.ico"
    mei = tmp_path / "mei"
    (mei / "assets").mkdir(parents=True)
    (mei / "assets" / "bob-systray.ico").write_bytes(b"ico")
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    assert bw.find_window_icon(tmp_path / "nowhere") == mei / "assets" / "bob-systray.ico"


def test_set_console_icon_never_raises_without_a_console_or_icon(tmp_path):
    import bob_worker as bw
    assert bw.set_console_icon(tmp_path / "nowhere") in (True, False)


@WIN
def test_start_menu_has_one_entry_start_systray():
    from test_start_menu_020 import EXPECTED
    assert EXPECTED["bob"] >= {"Start Systray"} and not any("Restart" in n or "Logs" in n for p in EXPECTED.values() for n in p)
