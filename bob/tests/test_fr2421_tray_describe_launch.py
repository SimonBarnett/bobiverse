"""FR #2421: TipForm BobTray.cs consumes bob-worker --describe-launch JSON."""
from __future__ import annotations

from repo_layout import ROOT


def test_bob_tray_has_try_describe_launch():
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    assert "static bool TryDescribeLaunch" in cs
    assert "--describe-launch" in cs
    assert "Common.ParseJson" in cs
    assert "fromPlan = TryDescribeLaunch" in cs or "TryDescribeLaunch(exe" in cs


def test_launch_prefers_plan_before_fallback_hash():
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    pref = cs.index("TryDescribeLaunch(exe")
    fallback = cs.index('new string[] { "--mode", mode, "--install-root", root }')
    assert pref < fallback
