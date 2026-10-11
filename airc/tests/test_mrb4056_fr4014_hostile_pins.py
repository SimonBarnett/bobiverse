"""Hostile pins for MRB #4056 / FR #4014 (additive after product merge)."""
from __future__ import annotations

from repo_layout import ROOT

SERVICE = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
INSTALL = (ROOT / "airc" / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8-sig")
START = (ROOT / "airc" / "scripts" / "Start-AircConsole.ps1").read_text(encoding="utf-8-sig")


def test_mrb4056_unregistered_log_uses_shop_and_wonderland():
    idx = SERVICE.find("is not registered")
    chunk = SERVICE[max(0, idx - 120) : idx + 160]
    assert "shop_channel" in chunk
    assert "wonderland" in chunk.lower()
    assert "FR #4014" in chunk or "FR #4014" in SERVICE


def test_mrb4056_warnings_name_wonderland_not_ionos():
    assert "instead of #ionos" not in INSTALL and "instead of #ionos" not in START
    assert "#wonderland" in INSTALL and "#wonderland" in START
    assert "Write-Warning" in INSTALL and "FR #4014" in INSTALL