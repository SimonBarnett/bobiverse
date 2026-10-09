"""FR #3762: same-version msiexec /i must still schedule RunInstall (maintenance mode).

Walrus: product registered after a failed install; second msiexec /i skipped RunInstall
because the CA condition was only ``NOT Installed OR REINSTALL`` (REINSTALL unset on
plain same-version /i). Broaden to run whenever not a full uninstall.
"""
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


def test_fr3762_pack_runinstall_runs_when_not_remove_all():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3762" in text
    # Must schedule SetInstallCmd + RunInstall on maintenance / same-version /i.
    assert (
        'Id="RunInstall"' in text
        and 'After="RollbackRecover">NOT REMOVE~="ALL"</Custom>' in text
    ) or (
        'Action="RunInstall"' in text and 'NOT REMOVE~="ALL"' in text
    )
    assert 'Action="SetInstallCmd"' in text and 'NOT REMOVE~="ALL"' in text
    # Old narrow condition must not remain on RunInstall / SetInstallCmd.
    for line in text.splitlines():
        if "Action=\"RunInstall\"" in line or "Action=\"SetInstallCmd\"" in line:
            assert "NOT Installed OR REINSTALL" not in line, line
            assert 'NOT REMOVE~="ALL"' in line, line


def test_fr3762_rollback_recover_aligned_with_runinstall():
    text = PACK.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if "Action=\"SetRollbackRecoverCmd\"" in line or "Action=\"RollbackRecover\"" in line:
            if "Custom Action=" in line:
                assert 'NOT REMOVE~="ALL"' in line, line


def test_fr3762_docs_and_skill_repair_path():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3762" in post
    assert "REINSTALL=ALL" in post or "msiexec /fa" in post or "/fa" in post
    assert "same-version" in post.lower() or "maintenance" in post.lower()
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3762" in skill
    assert "RunInstall" in skill or "REINSTALL" in skill


def test_fr3762_pack_ascii_no_bom():
    raw = PACK.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    # Allow UTF-8 BOM-less with only ASCII in the FR #3762 comment region - full file
    # may historically contain non-ASCII elsewhere; pin the new condition tokens as ASCII.
    assert b'NOT REMOVE~="ALL"' in raw
    assert b"FR #3762" in raw
