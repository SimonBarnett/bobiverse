"""FR #2669: tray vs CLI worker env parity — no doubled BOB_*_HOME; scrub CURSOR_/SAND_."""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import bob_worker as bw
from repo_layout import ROOT, resolve

# Prefer tracked bob/tray path; fall back to composed third_party alias.
FLEET = resolve("bob/tray/tools/Start-BobFleetTray.ps1")
if not FLEET.is_file():
    FLEET = resolve("third_party/bob-tray/tools/Start-BobFleetTray.ps1")


def test_fleet_tray_wrapper_does_not_double_backslashes(tmp_path):
    """Ensure-BobSystraySeatWrapper must emit single-backslash paths in single-quoted env assigns.

    FR #2928: must dot-source safely (Start-BobFleetTray main/tidy must not run).
    """
    root = tmp_path / "bob"
    tools = root / "tools"
    tools.mkdir(parents=True)
    (tools / "Watch-BobTray.ps1").write_text("# stub tray\n", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        . '{FLEET}'
        if (-not (Get-Command Ensure-BobSystraySeatWrapper -ErrorAction SilentlyContinue)) {{
          throw 'Ensure-BobSystraySeatWrapper missing after dot-source'
        }}
        $wrap = Ensure-BobSystraySeatWrapper -Root '{root}' -MachineId 'marchhare'
        Write-Output "WRAP=$wrap"
        Get-Content -LiteralPath $wrap -Raw
        """
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    # Must never have run tidy while loading the function.
    assert "tidy: Stop-BobSystrayPriorAgents" not in out
    assert "tidy: Cleanup-OrphanAgents" not in out
    # Wrapper must not contain C:\\Users style doubling inside the assigned string.
    fleet = FLEET.read_text(encoding="utf-8-sig")
    assert "FR #2669" in fleet
    assert "hasDoubledEnv" in fleet
    # Live assign lines must not use the old doubling form.
    assert ".Replace('\\', '\\\\')" not in fleet
    assert '.Replace("\\", "\\\\")' not in fleet
    body = out
    assert "BOB_BRIDGE_HOME" in body
    assert "BOB_IRC_HOME" in body
    # Doubled drive path like C:\\Users must not appear in generated wrapper content.
    assert re.search(r":\\\\", body) is None, body


def test_normalize_bob_home_path_collapses_doubled_slashes():
    assert bw.normalize_bob_home_path(r"C:\\Users\\Administrator\\.bobiverse") == r"C:\Users\Administrator\.bobiverse"
    assert bw.normalize_bob_home_path(r"C:\Users\Administrator\.bobiverse") == r"C:\Users\Administrator\.bobiverse"
    assert bw.normalize_bob_home_path("") == ""
    # UNC prefix preserved
    unc = bw.normalize_bob_home_path(r"\\server\share\x")
    assert unc.startswith(r"\\")
    assert "share" in unc


def test_normalize_bob_path_envs_keys():
    env = {
        "BOB_IRC_HOME": r"C:\\Users\\x\\.bobiverse",
        "BOB_BRIDGE_HOME": r"C:\\Users\\x\\.grok\\bob-bridge",
        "BOB_HOME": r"C:\\Users\\x\\.bobiverse",
        "AGENTIC_IRC_HOME": r"C:\\Users\\x\\.agentic-irc-bobiverse",
        "BOB_AI_ROOT": r"C:\\ai",
        "OTHER": r"C:\\keep\\doubled",
    }
    out = bw.normalize_bob_path_envs(env)
    assert out["BOB_IRC_HOME"] == r"C:\Users\x\.bobiverse"
    assert out["BOB_BRIDGE_HOME"] == r"C:\Users\x\.grok\bob-bridge"
    assert out["OTHER"] == r"C:\\keep\\doubled"  # untouched


def test_scrub_agent_host_env_removes_cursor_and_sand():
    env = {
        "PATH": "C:\\Windows",
        "CURSOR_API_KEY": "fake",
        "CURSOR_SOMETHING": "x",
        "SAND_TOKEN": "y",
        "BOB_MACHINE": "marchhare",
    }
    out = bw.scrub_agent_host_env(env)
    assert "CURSOR_API_KEY" not in out
    assert "CURSOR_SOMETHING" not in out
    assert "SAND_TOKEN" not in out
    assert out["PATH"] == "C:\\Windows"
    assert out["BOB_MACHINE"] == "marchhare"


def test_prepare_seat_child_env_combines_normalize_and_scrub():
    base = {
        "BOB_IRC_HOME": r"C:\\Users\\x\\.bobiverse",
        "CURSOR_FOO": "1",
        "SAND_BAR": "2",
        "PATH": "p",
    }
    out = bw.prepare_seat_child_env(base, {"BOB_OUTBOX": "o"})
    assert out["BOB_IRC_HOME"] == r"C:\Users\x\.bobiverse"
    assert "CURSOR_FOO" not in out
    assert "SAND_BAR" not in out
    assert out["BOB_OUTBOX"] == "o"
