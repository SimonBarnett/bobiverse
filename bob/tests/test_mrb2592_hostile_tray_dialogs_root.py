"""MRB #2592 hostile: BobTrayDialogs --root ArgumentList stays unquoted.

Product PR #2592 (FR #2590) removed the Start-Process quote-embed footgun.
Lock Dialogs + Fleet both pass unquoted --root via ArgumentList, and that
the old ('\"{0}\"' -f $Root) pattern does not return in Start-BobTrayDialog.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

DIALOGS = ROOT / "bob" / "tray" / "tools" / "BobTrayDialogs.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2592_dialogs_argumentlist_root_unquoted():
    t = _read(DIALOGS)
    fn = t[t.find("function Start-BobTrayDialog") :]
    fn = fn[: fn.find("\nfunction ")] if "\nfunction " in fn[1:] else fn
    assert "@('--root', $Root)" in fn or '@("--root", $Root)' in fn
    assert "Start-Process" in fn
    # Old footgun must stay gone inside Start-BobTrayDialog.
    assert not re.search(r"ArgumentList\s+@\(\s*'--root'\s*,\s*\(", fn)
    assert "('{0}\"'" not in fn.replace(" ", "")
    assert '("{0}"' not in fn or "--root" not in fn  # no format-quote of root in fn


def test_mrb2592_dialogs_no_format_quoted_root_anywhere():
    t = _read(DIALOGS)
    # Whole file: no ArgumentList pair that format-quotes the root value.
    assert "('--root', ('\"{0}\"' -f $Root))" not in t
    assert '("--root", ("{0}" -f $Root))' not in t
    assert "FR #2590" in t or "FR #2585" in t


def test_mrb2592_fleet_start_process_still_unquoted():
    t = _read(FLEET)
    assert "@('--root', $RepoRoot)" in t or '@("--root", $RepoRoot)' in t
    # CimMethod CommandLine may still shell-quote; that is intentional.
    assert '--root "{0}"' in t or "$exeArgs" in t
