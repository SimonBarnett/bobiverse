"""MRB #3775 hostile: FR #3762 RunInstall on same-version msiexec /i."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PIN = ROOT / "airc" / "tests" / "test_fr3762_runinstall_same_version_reinstall.py"


def test_mrb3775_hostile_pack_not_remove_all_contiguous():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3762" in text
    assert 'Action="SetInstallCmd"' in text
    assert 'Action="RunInstall"' in text
    # Contiguous schedule conditions for maintenance / same-version /i.
    assert 'After="InstallFiles">NOT REMOVE~="ALL"</Custom>' in text
    assert 'After="RollbackRecover">NOT REMOVE~="ALL"</Custom>' in text
    for line in text.splitlines():
        if 'Action="SetInstallCmd"' in line or 'Action="RunInstall"' in line:
            assert "NOT Installed OR REINSTALL" not in line, line
            assert 'NOT REMOVE~="ALL"' in line, line


def test_mrb3775_hostile_rollback_aligned():
    text = PACK.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if 'Action="SetRollbackRecoverCmd"' in line or 'Action="RollbackRecover"' in line:
            if "Custom Action=" in line:
                assert 'NOT REMOVE~="ALL"' in line, line
                assert "NOT Installed OR REINSTALL" not in line, line


def test_mrb3775_hostile_docs_skill_and_product_pin():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3762" in post
    assert "REINSTALL=ALL" in post or "/fa" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3762" in skill
    assert "NOT REMOVE" in skill or "RunInstall" in skill
    assert PIN.is_file()
    pin = PIN.read_text(encoding="utf-8")
    assert "NOT REMOVE~=" in pin or 'NOT REMOVE~="ALL"' in pin


def test_mrb3775_hostile_product_pin_ascii_no_bom():
    raw = PIN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    # Product pin should stay ASCII (3 non-ASCII chars were noted on tip — gate strict).
    non = [b for b in raw if b > 127]
    assert not non, f"non-ascii bytes at {[hex(b) for b in non[:8]]}"
