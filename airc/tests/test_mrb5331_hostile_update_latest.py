"""MRB #5331 hostile pins: FR #5280 S3 latest vs pin after main fold."""
from __future__ import annotations

from repo_layout import ROOT

CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
REMOTE = ROOT / "airc" / "docs" / "airc-remote-control.md"
UPD = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
VISION = ROOT / "airc" / "docs" / "feature-request-airc-remote-update-restart-2026-10-31.md"


def test_mrb5331_skill_and_docs_keep_5280_and_5281():
    cmd = CMD.read_text(encoding="utf-8")
    assert not CMD.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "<<<<<<<" not in cmd
    assert "FR #5280" in cmd
    assert "latest" in cmd.lower()
    assert "VERSION (FR #5281)" in cmd
    remote = REMOTE.read_text(encoding="utf-8")
    assert "FR #5280" in remote
    assert "releases/latest" in remote or "latest GitHub Release" in remote
    assert "TargetVersion" in remote
    vis = VISION.read_text(encoding="utf-8")
    assert "no version pin = latest" in vis or "Bare `UPDATE airc`" in vis


def test_mrb5331_updater_omitted_target_hits_latest_api():
    t = UPD.read_text(encoding="utf-8-sig")
    fn = t[t.index("function Get-LatestRelease") : t.index("function Test-AssetUrl")]
    assert "/releases/latest" in fn
    assert "FR #5280" in t
    assert "omit = latest" in t or "empty TargetVersion" in t
