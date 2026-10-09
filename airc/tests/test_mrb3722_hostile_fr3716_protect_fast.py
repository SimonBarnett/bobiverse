"""docs/mrb-3722: hostile pin FR #3716 skip ACL walk unless -Force."""
from __future__ import annotations

import re

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
PRODUCT = ROOT / "airc/tests/test_fr3716_protect_skip_acl_walk.py"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def test_mrb3722_common_early_return_gate_contiguous():
    t = COMMON.read_text(encoding="utf-8-sig")
    # Contiguous fast-path: Recurse + not Force + protected root -> skip walk.
    assert "$Recurse -and -not $Force" in t
    assert "FR #3716 skip ACL walk; root already protected" in t
    assert "FR #3678 skip takeown; root already protected" in t
    assert "[switch]$Force" in t
    # Param order keeps Force after FailClosed (Install-Airc named binds).
    m = re.search(
        r"param\(\s*\[Parameter\(Mandatory\)\]\[string\]\$Path,\s*"
        r"\[switch\]\$Recurse,\s*\[switch\]\$FailClosed,\s*\[switch\]\$Force\s*\)",
        t,
        re.S,
    )
    assert m, "Protect-BobiverseInstallTree param block must include [switch]$Force"


def test_mrb3722_install_airc_force_after_copy_before_start():
    t = INSTALL.read_text(encoding="utf-8-sig")
    hits = list(
        re.finditer(
            r"Protect-BobiverseInstallTree -Path \$InstallRoot -Recurse -Force -FailClosed",
            t,
        )
    )
    assert len(hits) == 1
    assert hits[0].start() > t.find("& $installLegacy")
    assert hits[0].start() < t.find("Start-Service -Name 'Airc'")
    assert "FR #3716" in t


def test_mrb3722_product_pin_skill_post():
    assert PRODUCT.is_file()
    p = PRODUCT.read_text(encoding="utf-8")
    assert "test_fr3716_common_skip_acl_walk_unless_force" in p
    assert "test_fr3716_install_airc_full_recurse_passes_force" in p
    skill = SKILL.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    assert "3716" in skill and "Force" in skill
    assert "3716" in post and "Get-Acl" in post
