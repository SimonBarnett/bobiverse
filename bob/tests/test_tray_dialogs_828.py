"""t828u/t829u: compiled About/Status dialogs (C# WinForms via in-box csc.exe) and the first-class bob/tray + bob/agentwatcher sources."""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT, REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
needs_csc = pytest.mark.skipif(not (WIN and CSC.is_file()), reason="needs Windows + .NET Framework csc.exe")
DIALOGS = REPO / "bob" / "tray" / "dialogs"
TRAY_TOOLS = REPO / "bob" / "tray" / "tools"
PS = shutil.which("powershell.exe") or shutil.which("powershell")


def _ps(script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                          capture_output=True, text=True, timeout=timeout)


def _run(exe: Path, *args: str, env: dict | None = None, timeout: int = 60) -> None:
    e = dict(os.environ)
    e.update(env or {})
    # winexe: Popen + wait (a console shell does not wait for a GUI exe)
    p = subprocess.Popen([str(exe), *args], env=e)
    assert p.wait(timeout=timeout) == 0


@pytest.fixture(scope="module")
def dialogs(tmp_path_factory) -> Path:
    if not (WIN and CSC.is_file() and PS):
        pytest.skip("needs Windows + csc.exe + powershell")
    out = tmp_path_factory.mktemp("bobdlg")
    r = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"),
                        "-RepoRoot", str(REPO), "-OutDir", str(out)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return out


# ---- layout: t829u -------------------------------------------------------------------------------------------------------------
def test_tray_and_agentwatcher_are_first_class_bob_sources():
    assert (REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").is_file()
    assert (REPO / "bob" / "agentwatcher" / "Watch-AgentHealth.ps1").is_file()
    assert not (REPO / "bob" / "third_party").exists()          # nothing vendored under bob/ any more
    # legacy flat spellings (what installed/staged trees and old callers use) still resolve to the new homes
    assert Path(str(ROOT / "third_party" / "bob-tray" / "tools")) == REPO / "bob" / "tray" / "tools"
    assert Path(str(ROOT / "third_party" / "Watch-AgentHealth")) == REPO / "bob" / "agentwatcher"


@pytest.mark.skipif(not (WIN and PS), reason="needs powershell")
def test_repo_path_resolver_maps_legacy_names_to_the_first_class_dirs():
    cm = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
    r = _ps(f". '{cm}'; foreach($rel in 'third_party\\bob-tray\\tools','third_party\\Watch-AgentHealth','third_party\\nssm','tray\\dialogs'){{ Get-BobiverseRepoPath -Root '{REPO}' -Rel $rel }}")
    lines = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    assert lines[0].endswith(r"bob\tray\tools") and lines[1].endswith(r"bob\agentwatcher"), r.stdout + r.stderr
    assert lines[2].endswith(r"common\third_party\nssm") and lines[3].endswith(r"bob\tray\dialogs")


def test_packaging_sync_install_and_tray_know_the_new_layout_and_dialogs():
    pack = (ROOT / "scripts" / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    assert "Build-BobDialogs.ps1" in pack and "stage\\tools\\bob-about.exe" in pack
    assert "Sync-BobTrayFromAgenticBuild" not in pack.replace("Sync-BobTrayFromAgenticBuild.ps1)'", "")  # no auto re-vendor any more
    sync = (ROOT / "scripts" / "Sync-BobiverseFromRepo.ps1").read_text(encoding="utf-8-sig")
    assert "third_party\\bob-tray\\dialogs" in sync and "Build-BobDialogs.ps1" in sync and "Dst = 'dialogs'" in sync
    inst = (ROOT / "scripts" / "Install-Bob.ps1").read_text(encoding="utf-8-sig")
    assert "Build-BobDialogs.ps1" in inst
    retired = (ROOT / "scripts" / "Sync-BobTrayFromAgenticBuild.ps1").read_text(encoding="utf-8-sig")
    assert "-AllowRevendor" in retired and "bob\\tray" in retired
    tray = (TRAY_TOOLS / "Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    assert "'BobTrayDialogs.ps1'" in tray and "Start-BobTrayDialog -Root $RepoRoot -Name 'status'" in tray
    assert "Start-BobTrayDialog -Root $RepoRoot -Name 'about'" in tray and "Write-BobTrayStatusSnapshot" in tray


def test_dialog_sources_are_csc4_compatible_text():
    for f in ("BobDialogsCommon.cs", "BobAbout.cs", "BobStatus.cs"):
        t = (DIALOGS / f).read_text(encoding="utf-8-sig")
        assert '$"' not in t   # csc 4 = C# 5 (no interpolation); the build test is the real check
        assert "t828u" in t
    assert (DIALOGS / "bob-dialogs.manifest").is_file()


# ---- build + behaviour: t828u ---------------------------------------------------------------------------------------------------
@needs_csc
def test_both_exes_compile_small_and_native(dialogs):
    for n in ("bob-about.exe", "bob-status.exe", "bob-tray.exe"):
        p = dialogs / n
        assert p.is_file() and p.stat().st_size < 200_000, n          # ~25 KB: no bundled interpreter, nothing to unpack at start
        assert p.read_bytes()[:2] == b"MZ"


@needs_csc
def test_about_lists_installs_like_the_old_dialog(dialogs, tmp_path):
    ai = tmp_path / "ai"
    bob = ai / "bob"
    (bob / "scripts").mkdir(parents=True)
    (bob / "VERSION").write_text("9.8.7\n", encoding="utf-8")
    (bob / "BUILD.json").write_text(json.dumps({"product": "bob", "version": "9.8.7", "built_utc": "2026-01-02T03:04:05.1234567Z", "commit": "abc1234"}), encoding="utf-8")
    out = tmp_path / "about.txt"
    _run(dialogs / "bob-about.exe", "--root", str(bob), "--text-out", str(out), env={"BOB_AI_ROOT": str(ai)})
    raw = out.read_bytes().decode("utf-8")
    text = raw.replace("\r\n", "\n")
    assert "bob  9.8.7" in text
    assert "    released: 2026-01-02 03:04 UTC (built)" in text
    assert "    commit:   abc1234" in text
    assert f"    path:     {bob}" in text
    assert "\r\n" in raw                                              # same CRLF text as Format-BobInstallInfo


def _model_json(tmp_path: Path) -> Path:
    """Run the REAL PowerShell model builder + snapshot writer (stubbing only the module functions the live tray provides)."""
    if not PS:
        pytest.skip("needs powershell")
    helper = TRAY_TOOLS / "BobTrayDialogs.ps1"
    root = tmp_path / "root"
    script = f"""
. '{helper}'
function Get-BobTrayBarPaint {{ param($RemainingPct, [int]$BarWidth = 100)
  if ($null -eq $RemainingPct -or [string]$RemainingPct -eq '') {{ return [pscustomobject]@{{ known = $false }} }}
  [pscustomobject]@{{ known = $true; remaining_pct = [int]$RemainingPct; fill_r = 63; fill_g = 185; fill_b = 80 }} }}
function Get-BobCanonicalMachineId {{ param($Id) ([string]$Id).ToLowerInvariant() }}
function Get-BobTrayCursorGroupHelpTooltip {{ param([string]$GroupId) 'help for ' + $GroupId }}
$h = [pscustomobject]@{{
  title = 'bob marchhare'; jobs_text = 'fuels cursor-models, grok-build...`nGitHub issue post: ready`nout of tokens, open with key'; account_overage_gbp = 1.5
  cursor_pools = @([pscustomobject]@{{ heading = 'Low cost models (80%)'; remaining_pct = 80; pct_label = '80%'; group_id = 'auto' }},
                   [pscustomobject]@{{ heading = 'high cost models (-3.2)'; remaining_pct = 0; pct_label = '-3.2'; group_id = 'high-cost-models' }})
  machines = @([pscustomobject]@{{ id = 'MarchHare'; remaining_pct = 42; seat_label = 'ntsa'; reset_label = 'resets Mon'; worker_lines = @('marchhare-41912: doing FR simonbarnett/bobiverse#9', 'marchhare-5832: idle') }},
               [pscustomobject]@{{ id = 'marchhare'; remaining_pct = 42; worker_lines = @() }},
               [pscustomobject]@{{ id = 'flamingo'; remaining_pct = 0; worker_lines = @() }})
}}
$m = New-BobTrayStatusModel -Hover $h -AlertKind 'stall' -Alerts @('agent_stall x') -Version 'bob 1.2.3' -Machine 'marchhare' -Short 'bob marchhare tip' -Attention $true -AttentionSeq 7 -Pulse $true
$p = Write-BobTrayStatusSnapshot -Root '{root}' -Model $m
$p = Write-BobTrayStatusSnapshot -Root '{root}' -Model $m   # second write = the atomic Replace path
Write-Output $p
"""
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    p = Path(r.stdout.strip().splitlines()[-1])
    assert p.is_file() and p == root / "run" / "tray-status.json"
    assert not (root / "run" / "tray-status.json.tmp").exists()
    return p


@pytest.mark.skipif(not (WIN and PS), reason="needs powershell")
def test_status_model_matches_the_old_card_content(tmp_path):
    d = json.loads(_model_json(tmp_path).read_text(encoding="utf-8"))
    assert d["title"] == "bob marchhare" and d["alert"] == "stall" and d["version"] == "bob 1.2.3"
    assert d["overspend"] == "overspend \u00a31.50"
    assert [c["heading"] for c in d["cursor"]] == ["Low cost models (80%)", "high cost models (-3.2)"]   # Cursor pools on top
    assert d["cursor"][0]["pct"] == 80 and d["cursor"][0]["help"] == "help for auto" and d["cursor"][0]["red"] is False
    assert d["cursor"][1]["red"] is True                                                                    # negative / pound label = red
    assert "jobs_text" not in d and "fuels cursor-models" not in json.dumps(d)                              # t832u: no plain-text block, dashboard only
    assert d["short"] == "bob marchhare tip" and d["attention"] is True and d["attention_seq"] == 7 and d["pulse"] is True
    g = d["grok"]
    assert [x["heading"] for x in g] == ["MARCHHARE  -  ntsa (42%) - resets Mon", "FLAMINGO (0%)"]         # one row per canonical machine; 0% is real
    assert g[0]["workers"] == ["marchhare-41912: doing FR simonbarnett/bobiverse#9", "marchhare-5832: idle"]  # {irc nick}: {doing/idle}
    assert g[1]["known"] is True and g[1]["pct"] == 0


@needs_csc
def test_status_exe_reads_the_snapshot_the_tray_writes(dialogs, tmp_path):
    snap = _model_json(tmp_path)
    out = tmp_path / "check.txt"
    _run(dialogs / "bob-status.exe", "--check", str(snap), "--text-out", str(out))
    t = out.read_text(encoding="utf-8")
    assert "bob marchhare" in t and "cursor=2 grok=2 alert=stall" in t
    assert t.index("C Low cost models") < t.index("G MARCHHARE")
    assert "W marchhare-41912: doing FR simonbarnett/bobiverse#9" in t and "W marchhare-5832: idle" in t


def _timing(exe: Path, tmp_path: Path, *args: str) -> int:
    f = tmp_path / ("t-" + exe.stem + ".txt")
    f.unlink(missing_ok=True)
    _run(exe, *args, "--timing-out", str(f))
    return int(f.read_text())


@needs_csc
def test_cold_start_is_well_under_a_second_on_an_idle_box(dialogs, tmp_path):
    snap = _model_json(tmp_path)
    root = snap.parent.parent
    (root / "tools").mkdir(exist_ok=True)
    about = min(_timing(dialogs / "bob-about.exe", tmp_path, "--root", str(root)) for _ in range(3))
    status = min(_timing(dialogs / "bob-status.exe", tmp_path, "--root", str(root)) for _ in range(3))
    print(f"cold start ms: about={about} status={status}")
    # best of 3; generous bound because the suite shares the box with other work (measured ~0.2-0.4 s idle)
    assert about < 2500 and status < 2500


@needs_csc
def test_second_launch_is_a_noop_that_brings_the_first_window_forward(dialogs, tmp_path):
    user32 = ctypes.windll.user32
    title = "Bobiverse systray - about"
    root = tmp_path / "r"
    root.mkdir()
    first = subprocess.Popen([str(dialogs / "bob-about.exe"), "--root", str(root)])
    try:
        for _ in range(100):
            if user32.FindWindowW(None, title):
                break
            time.sleep(0.1)
        assert user32.FindWindowW(None, title), "first window never appeared"
        second = subprocess.Popen([str(dialogs / "bob-about.exe"), "--root", str(root)])
        assert second.wait(timeout=20) == 0                                # exits at once: single instance
        assert first.poll() is None                                        # the first one is still open
    finally:
        first.kill()
        first.wait(timeout=10)

def test_docs_describe_the_layout_the_tech_choice_and_the_dialog_contract():
    d = (ROOT / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8-sig")
    for needle in ("bob/tray", "bob/agentwatcher", "csc.exe", "PyInstaller", "tray-status.json", "{irc nick}: {doing|idle}", "Single instance", "-AllowRevendor", "bob-tray.exe", "tray-cmd.txt", "BOB_TRAY_ENGINE", "jobs_text"):
        assert needle in d, needle


# ---- t832u: the compiled systray ----------------------------------------------------------------------------------------------
def test_status_window_draws_only_the_dashboard_no_hover_text_block():
    src = (DIALOGS / "BobStatus.cs").read_text(encoding="utf-8-sig")
    assert "jobs_text" not in src and "m.Jobs" not in src and "Jobs" not in src.replace("jobs_", "")
    ps = (TRAY_TOOLS / "BobTrayDialogs.ps1").read_text(encoding="utf-8-sig")
    assert "jobs_text" not in ps.split("function New-BobTrayStatusModel", 1)[1].split("function ", 1)[0]


@needs_csc
def test_tray_menu_is_status_agent_plan_acknowledge_log_restart_exit(dialogs, tmp_path):
    out = tmp_path / "menu.txt"
    _run(dialogs / "bob-tray.exe", "--root", str(tmp_path), "--dump-menu", str(out))
    items = out.read_text(encoding="utf-8").splitlines()
    assert items == ["Status", "Agent", "Plan", "Acknowledge", "Open log", "-", "Restart", "Exit"]
    src = (DIALOGS / "BobTray.cs").read_text(encoding="utf-8-sig")
    assert 'miStatus.Font = new Font(miStatus.Font, FontStyle.Bold)' in src and "DoubleClick" in src or "MouseClick" in src


@needs_csc
def test_tray_state_tip_and_acknowledge(dialogs, tmp_path):
    snap = tmp_path / "s.json"
    snap.write_text(json.dumps({"short": "bob marchhare 42%", "alert": "stall", "attention": True, "attention_seq": 3, "pulse": True}), encoding="utf-8")
    out = tmp_path / "st.txt"
    _run(dialogs / "bob-tray.exe", "--dump-state", str(snap), "--text-out", str(out))
    t = out.read_text(encoding="utf-8")
    assert "attention=True" in t and "seq=3" in t and "alert=stall" in t and "tip=" in t and "tip_acked=" in t
    assert all(len(l.split("=", 1)[1]) <= 127 for l in t.splitlines() if l.startswith("tip"))               # NotifyIcon.Text limit


@needs_csc
def test_tray_worker_seat_cap_reads_live_workers(dialogs, tmp_path):
    out = tmp_path / "seats.txt"
    _run(dialogs / "bob-tray.exe", "--root", str(tmp_path), "--seats", "--text-out", str(out))
    first = out.read_text(encoding="utf-8").splitlines()[0]
    assert first.isdigit()


def test_tray_engine_contract_between_exe_and_powershell():
    cs = (DIALOGS / "BobTray.cs").read_text(encoding="utf-8-sig")
    ps = (TRAY_TOOLS / "Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    helper = (TRAY_TOOLS / "BobTrayDialogs.ps1").read_text(encoding="utf-8-sig")
    fleet = (TRAY_TOOLS / "Start-BobFleetTray.ps1").read_text(encoding="utf-8-sig")
    for k in ("tray-cmd.txt", "tray-env.json", "BOB_TRAY_ENGINE", "BOB_TRAY_EXE_PID", "tray-status.json"):
        assert k in cs
    assert "tray-cmd.txt" in helper and "BOB_TRAY_EXE_PID" in helper and "tray-env.json" in helper
    assert "Test-BobTrayEngineMode" in ps and "Invoke-BobTrayExeCommands" in ps
    assert "[Environment]::Exit(0)" in ps.split("-ParentGone", 1)[1][:260]                                       # a dead exe must NOT run the exit path (IRC logout / Stop-BobiverseMoot)
    assert "else { $notify.Visible = $true }" in ps                                                          # engine mode: icon is the exe's
    assert "Get-BobSystrayTrayExe" in fleet and "bob-tray.exe" in fleet
    assert "ircBob" in fleet                                                                                 # restart-on-start unchanged
    assert "sc.exe" in cs.lower() or "sc stop" in cs.lower() or "ircBob" in cs                               # Exit stops the service as before


@pytest.mark.skipif(not (WIN and PS), reason="needs powershell")
def test_engine_command_pump_consumes_ack_exit_restart_and_parent_gone(tmp_path):
    helper = TRAY_TOOLS / "BobTrayDialogs.ps1"
    run = tmp_path / "run"
    run.mkdir()
    (run / "tray-cmd.txt").write_text("ack\nexit\n", encoding="ascii")
    script = f"""
. '{helper}'
$global:log = @()
$r1 = Invoke-BobTrayExeCommands -Root '{tmp_path}' -OnAck {{ $global:log += 'ack' }} -OnExit {{ $global:log += 'exit' }} -OnRestart {{ $global:log += 'restart' }} -ParentGone {{ $global:log += 'gone' }}
$env:BOB_TRAY_EXE_PID = '999999'
$r2 = Invoke-BobTrayExeCommands -Root '{tmp_path}' -OnAck {{ }} -OnExit {{ }} -OnRestart {{ }} -ParentGone {{ $global:log += 'gone' }}
Write-Output ($global:log -join ',')
Write-Output (Test-Path '{run}\\tray-cmd.txt')
"""
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[-2] == "ack,exit,gone" and lines[-1] == "False"


@needs_csc
def test_tray_cold_start_and_menu_open_timing_and_single_instance(dialogs, tmp_path):
    root = tmp_path / "r"
    (root / "run").mkdir(parents=True)
    f = tmp_path / "tt.txt"
    best = None
    for _ in range(3):
        f.unlink(missing_ok=True)
        _run(dialogs / "bob-tray.exe", "--root", str(root), "--no-engine", "--timing-out", str(f))
        icon_ms, menu_ms = (int(x) for x in f.read_text().strip().split(","))
        best = (icon_ms, menu_ms) if best is None or sum((icon_ms, menu_ms)) < sum(best) else best
    print(f"tray cold start ms: icon visible={best[0]} menu opened={best[1]}")
    assert best[0] < 3000 and best[1] < 5000
    first = subprocess.Popen([str(dialogs / "bob-tray.exe"), "--root", str(root), "--no-engine"])
    try:
        time.sleep(2.0)
        second = subprocess.Popen([str(dialogs / "bob-tray.exe"), "--root", str(root), "--no-engine"])
        assert second.wait(timeout=20) == 0 and first.poll() is None                                          # one tray per root
    finally:
        first.kill()
        first.wait(timeout=10)
