"""FR #5196: bob MSI/install must set NSSM AppDirectory for ircBob."""
from __future__ import annotations

from repo_layout import ROOT

INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"


def test_install_bob_sets_nssm_appdirectory():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "AppDirectory" in text
    assert "FR #5196" in text
    assert "Join-Path $InstallRoot 'scripts')" in text or 'Join-Path $InstallRoot "scripts")' in text
    # Keep setting after nssm install so a re-register does not leave AppDirectory unset.
    assert text.index("nssm") < text.lower().index("appdirectory") or "set', $ServiceName, 'AppDirectory'" in text
