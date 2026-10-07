"""Hostile MRB #2983: MSI payload wins over stale install-tree git (FR #2982)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

POST = ROOT / "common" / "docs" / "post-install.md"
SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2983_install_scripts_msi_product_version_forces_skipcopy():
    for rel in (
        "bob/scripts/Install-Bob.ps1",
        "jeeves/scripts/Install-Jeeves.ps1",
        "airc/scripts/Install-Airc.ps1",
    ):
        t = _read(ROOT / rel)
        assert "FR #2982" in t, rel
        assert "MsiProductVersion" in t, rel
        idx = t.index("MsiProductVersion")
        assert "$SkipCopy = $true" in t[idx:] or "SkipCopy = $true" in t[idx:], rel


def test_mrb2983_install_bob_skips_tray_under_installroot():
    t = _read(ROOT / "bob" / "scripts" / "Install-Bob.ps1")
    assert "trayUnderInstall" in t or "StartsWith" in t
    assert "FR #2982" in t


def test_mrb2983_sync_skip_stale_worktree_and_post_install():
    sync = _read(SYNC)
    assert "sync-skip-stale-worktree" in sync
    assert "FR #2982" in sync
    # Tip updater overlay still runs when compose is skipped
    assert "skipStaleCompose" in sync or "skip-stale" in sync
    post = _read(POST)
    assert "FR #2982" in post
    assert "SkipCopy" in post or "MsiProductVersion" in post
    raw = POST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
