"""FR #3741: CAQuietExec64 SetInstallCmd must start with a quoted executable path.

WiX QuietExec parses the leading \"...\" token; an unquoted cmd.exe /d /c call
returns E_INVALIDARG (0x80070057) and msiexec 1603 (airc-0.1.28).
Keep FR #3685 cmd /d /c call exit propagation.
"""
from __future__ import annotations

import re

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"


def test_fr3741_setinstallcmd_value_starts_with_quoted_cmd():
    p = PACK.read_text(encoding="utf-8-sig")
    i = p.find('Id="SetInstallCmd"')
    assert i >= 0, "SetInstallCmd CustomAction missing"
    window = p[i : i + 500]
    # Contiguous Value= must open with quoted System64Folder cmd.exe (or ComSpec).
    assert 'Value="&quot;[System64Folder]cmd.exe&quot; /d /c call' in window or (
        'Value="&quot;[%ComSpec]&quot; /d /c call' in window
    ), window
    assert "&quot;[INSTALLDIR]scripts\\$installCmd&quot;$installArgs" in window
    assert "FR #3741" in p or "3741" in p
    # Must not regress to bare unquoted cmd.exe as the first QuietExec token.
    assert not re.search(
        r'Id="SetInstallCmd"[^>]*Value="cmd\.exe /d /c call',
        p,
    )


def test_fr3741_runinstall_still_return_check():
    p = PACK.read_text(encoding="utf-8-sig")
    assert 'Id="RunInstall"' in p
    assert 'Return="check"' in p
    assert "CAQuietExec64" in p
