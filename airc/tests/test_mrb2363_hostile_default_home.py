"""MRB #2363 hostile: Default ConsoleHome remap + DisplayName expansion gates (FR #2355)."""
from __future__ import annotations

import re

from repo_layout import ROOT


def _install() -> str:
    return (ROOT / "airc" / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8-sig")


def _update() -> str:
    return (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(
        encoding="utf-8-sig"
    )


def test_mrb2363_display_name_uses_expanded_machine_id():
    t = _install()
    assert "airc console (#{machine} IRC shell)" not in t
    assert re.search(
        r'\$displayName\s*=\s*"airc console \(#\$\{dnMachine\} IRC shell\)"', t
    )
    # NSSM set uses the expanded variable, not a literal placeholder.
    assert re.search(r"@\('DisplayName',\s*\$displayName\)", t)


def test_mrb2363_default_home_regex_matches_orphan_paths():
    # Mirror Test-AircDefaultProfileHome from Install-AircConsole.ps1
    rx = re.compile(r"(?i)(?:^|[\\/])Users[\\/]Default(?:[\\/]|$)")
    bad = [
        r"C:\Users\Default\.airc",
        r"C:/Users/Default/.airc",
        r"C:\Users\Default\.airc\console.password",
        r"D:\Users\Default\foo",
    ]
    ok = [
        r"C:\ai\airc\home",
        r"C:\Users\Administrator\.airc",
        r"C:\Users\Defaulted\.airc",  # must not false-positive
        r"C:\Users\DefaultUser\.airc",
    ]
    for p in bad:
        assert rx.search(p), p
    for p in ok:
        assert not rx.search(p), p


def test_mrb2363_remap_runs_after_consolehome_resolved():
    t = _install()
    i_new = t.index("New-Item -ItemType Directory -Force -Path $ConsoleHome")
    i_remap = t.index("FR #2355: remap even when")
    assert i_remap > i_new
    assert "Resolve-AircSafeConsoleHome" in t[i_remap : i_remap + 800]


def test_mrb2363_identity_reconcile_continues_past_default_consolehome():
    t = _update()
    assert "FR #2355: never restore ConsoleHome under Users\\Default" in t
    i = t.index("identity-reconcile skip ConsoleHome under Users\\Default")
    window = t[max(0, i - 200) : i + 250]
    assert "continue" in window
    # Must not fall through to restoring Default as previous value in that branch.
    before_continue = window.split("continue", 1)[0]
    assert "restoring the previous value" not in before_continue
