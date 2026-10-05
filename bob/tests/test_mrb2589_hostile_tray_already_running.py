"""MRB #2589 hostile: CimMethod CommandLine quoting vs Start-Process argv + mutex.

Product PR #2589 landed NormalizeRoot / already-running. These gates lock:
- Win32_Process.Create may shell-quote --root in CommandLine (correct).
- Start-Process ArgumentList fallback must stay unquoted.
- NormalizeRoot must keep Trim('"') so CimMethod-quoted argv still mutex-matches.
- Dual detect: Name/CommandLine without requiring ExecutablePath.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

COMMON_CS = ROOT / "bob" / "tray" / "dialogs" / "BobDialogsCommon.cs"
BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
LIFE = ROOT / "bob" / "tray" / "tools" / "BobTrayLifecycle.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2589_cimmethod_commandline_may_quote_root():
    t = _read(FLEET)
    # Shell quoting inside Win32 CommandLine is required for paths with spaces.
    assert re.search(r"\$exeArgs\s*=\s*'--root \"\{0\}\"'", t) or '--root "{0}"' in t
    assert "Invoke-CimMethod" in t and "Win32_Process" in t and "Create" in t


def test_mrb2589_start_process_fallback_root_unquoted():
    t = _read(FLEET)
    assert "@('--root', $RepoRoot)" in t or '@("--root", $RepoRoot)' in t
    # Must not reintroduce ArgumentList quote-embedding for the tray exe fallback.
    assert not re.search(
        r"ArgumentList\s+@\(\s*'--root'\s*,\s*\('\s*\"\{0\}\"'\s*-f",
        t,
    )


def test_mrb2589_normalize_root_strips_quotes_for_cim_argv():
    t = _read(COMMON_CS)
    assert "NormalizeRoot" in t and "TrayMutexKey" in t
    # CimMethod Create still embeds quotes in --root; mutex key must strip them.
    assert 'Trim(\'"\')' in t or 'Trim("' in t or "Trim('\"')" in t
    assert "GetFullPath" in t
    assert "TrimEnd" in t


def test_mrb2589_already_running_before_tray_up():
    t = _read(BOB_TRAY)
    body = t[t.find("static int Main") :]
    fail_idx = body.find("already-running")
    up_idx = body.find('Write("tray-up"')
    assert fail_idx >= 0
    assert up_idx > fail_idx


def test_mrb2589_dual_detect_name_or_commandline():
    fleet = _read(FLEET)
    life = _read(LIFE)
    # ExecutablePath often null on CIM; Name or CommandLine must be enough.
    for label, t in (("fleet", fleet), ("life", life)):
        assert "bob-tray.exe" in t, label
        assert not re.search(
            r"Name\s+-eq\s+'bob-tray\.exe'\s+-and\s+\$_\.ExecutablePath",
            t,
        ), label
