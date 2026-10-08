"""docs/mrb-3477: hostile pins for FR #3462 client/workstation sync force-off."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"
PRODUCT_TEST = ROOT / "airc/tests/test_fr3401_client_profile.py"


def test_mrb3477_install_order_force_sync_before_prior():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3462" in t
    force = "elseif ($prof -in @('workstation', 'client')) { $resolvedSync = $false }"
    assert force in t
    i_exp = t.index("if ($null -ne $expSync) { $resolvedSync = [bool]$expSync }")
    i_force = t.index(force)
    i_prior = t.index("elseif ($null -ne $priorSync) { $resolvedSync = [bool]$priorSync }")
    assert i_exp < i_force < i_prior


def test_mrb3477_skill_and_post_install_document_3462():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3401 / #3462" in skill or ("FR #3462" in skill and "sync_from_repo=false" in skill)
    assert "ignore prior fleet" in skill.lower() or "unless MSI/CLI explicit" in skill
    post = POST.read_text(encoding="utf-8")
    assert "FR #3462" in post
    assert "ignore prior fleet" in post.lower() or "unless MSI/CLI" in post


def test_mrb3477_product_pin_test_present():
    t = PRODUCT_TEST.read_text(encoding="utf-8")
    assert "test_fr3462_client_workstation_force_sync_off_ignore_prior" in t
    assert "FR #3462" in t
