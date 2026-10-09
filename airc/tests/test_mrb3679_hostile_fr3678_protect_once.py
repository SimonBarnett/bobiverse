"""docs/mrb-3679: hostile pins for FR #3678 Install-Airc one Full Protect (PR #3679)."""
from __future__ import annotations

import re

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
PRODUCT = ROOT / "airc/tests/test_fr3678_protect_skip_takeown_once.py"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_mrb3679_install_airc_protect_shape():
    t = INSTALL.read_text(encoding="utf-8-sig")
    early = t.find("Protect-BobiverseInstallTree -Path $InstallRoot -FailClosed")
    assert early > 0
    assert "-Recurse" not in t[early : early + 80]
    recurse = list(
        re.finditer(
            r"Protect-BobiverseInstallTree -Path \$InstallRoot -Recurse -FailClosed",
            t,
        )
    )
    assert len(recurse) == 1
    assert recurse[0].start() > t.find("& $installLegacy")
    assert recurse[0].start() < t.find("Start-Service -Name 'Airc'")


def test_mrb3679_common_skip_takeown_and_elapsed():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Test-BobiverseInstallPathProtectedTarget" in t
    assert "skip takeown; root already protected" in t
    assert "elapsed_ms" in t
    assert "skipped_acl" in t
    assert "$Recurse -and $item.PSIsContainer" in t
    assert "/R /D Y" in t


def test_mrb3679_product_pin_and_skill():
    assert PRODUCT.is_file()
    p = PRODUCT.read_text(encoding="utf-8")
    assert "test_fr3678_install_airc_one_full_recurse_before_start" in p
    assert "test_fr3678_common_skips_takeown_when_already_protected" in p
    skill = SKILL.read_text(encoding="utf-8")
    assert "3678" in skill
    assert "takeown" in skill.lower()