"""MRB #3744 hostile pins for FR #3741 QuietExec quoted SetInstallCmd.

After product merge #3744:
- SetInstallCmd Value opens with quoted [System64Folder]cmd.exe (or ComSpec)
- FR #3685 /d /c call + Return=check remain contiguous
- Uninstall CA first token stays quoted (never regress install-only)
- Fleet-ops known-failure row names 0x80070057 / FR #3741
"""
from __future__ import annotations

import re

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
POST = ROOT / "common/docs/post-install.md"
AIRC = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_mrb3744_setinstallcmd_quoted_system64_contiguous():
    p = PACK.read_text(encoding="utf-8-sig")
    needle = (
        'Id="SetInstallCmd" Property="RunInstall" '
        'Value="&quot;[System64Folder]cmd.exe&quot; /d /c call '
        '&quot;[INSTALLDIR]scripts\\$installCmd&quot;$installArgs"'
    )
    assert needle in p, "SetInstallCmd QuietExec first token must stay quoted System64Folder cmd.exe"
    assert 'Id="RunInstall"' in p and 'Return="check"' in p and "CAQuietExec64" in p
    assert "FR #3741" in p
    assert not re.search(r'Id="SetInstallCmd"[^>]*Value="cmd\.exe ', p)


def test_mrb3744_uninstall_and_rollback_first_token_quoted():
    p = PACK.read_text(encoding="utf-8-sig")
    assert 'Id="SetUninstallCmd"' in p
    assert 'Value="&quot;[INSTALLDIR]scripts\\Uninstall-Airc.cmd&quot;' in p
    assert 'Value="&quot;[INSTALLDIR]scripts\\Recover-BobiverseService.cmd&quot;' in p


def test_mrb3744_docs_skill_known_failure_row():
    fleet = FLEET.read_text(encoding="utf-8")
    assert "0x80070057" in fleet and "FR #3741" in fleet
    post = POST.read_text(encoding="utf-8")
    assert "System64Folder" in post and "3741" in post
    skill = AIRC.read_text(encoding="utf-8")
    assert "3741" in skill and ("QuietExec" in skill or "0x80070057" in skill)
