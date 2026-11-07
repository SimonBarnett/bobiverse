"""FR #6142 / FR-002: canonical digest URL https://bob.ntsa.uk/bob/v1/report.

Static source pins (no PowerShell / no network). IRC host stays irc.ntsa.uk.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = "https://bob.ntsa.uk/bob/v1/report"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
WEBHOOK = ROOT / "tray" / "src" / "Private" / "Invoke-BobDigestWebhook.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
CFG = ROOT / "tray" / "config" / "bobiverse.json"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr002_get_bob_digest_url_fallback_is_bob_host():
    irc = _txt(IRC)
    start = irc.index("function Get-BobDigestUrl")
    block = irc[start : start + 900]
    assert CANON in block
    assert "bob.ntsa.uk" in block
    assert "irc.ntsa.uk/bob/v1/report" not in block


def test_fr002_tray_digest_report_url_trims_before_blank_check():
    w = _txt(WATCH)
    start = w.index("function Get-BobTrayDigestReportUrl")
    block = w[start : start + 350]
    assert CANON in block
    assert "FR #6142" in block
    # Trim before truthiness / blank check (whitespace-only env must not win).
    assert ".Trim()" in block
    trim_at = block.index(".Trim()")
    # After trim, blank check uses the trimmed value (if ($u) / if (-not $u)).
    assert "if ($u)" in block[trim_at:] or "if (-not $u)" in block[trim_at:]


def test_fr002_dialogs_sync_fallback_is_bob_host():
    d = _txt(DIALOGS)
    start = d.index("function Sync-BobTrayStatusWorkersFromDigest")
    block = d[start : start + 1200]
    assert CANON in block
    assert "FR #6142" in block
    assert ".Trim()" in block


def test_fr002_packaged_config_reporturl_and_irc_host():
    cfg = json.loads(_txt(CFG))
    assert cfg.get("reportUrl") == CANON
    assert cfg.get("host") == "irc.ntsa.uk"
    assert "irc.ntsa.uk" not in str(cfg.get("reportUrl") or "")


def test_fr002_post_selectors_have_no_irc_report_fallback():
    """POST selectors must not invent a live-host default (config/env only)."""
    irc = _txt(IRC)
    post = irc[irc.index("function Get-BobDigestReportUrl") : irc.index("function Get-BobDigestReportUrl") + 500]
    assert "return $null" in post
    assert "irc.ntsa.uk/bob/v1/report" not in post
    # Packaged SoT comment (FR #6142).
    assert "reportUrl" in post and ("SoT" in post or "source of truth" in post.lower() or "FR #6142" in post)

    wh = _txt(WEBHOOK)
    wpost = wh[wh.index("function Get-BobDigestWebhookReportUrl") : wh.index("function Get-BobDigestWebhookReportUrl") + 450]
    assert "return $null" in wpost
    assert "irc.ntsa.uk/bob/v1/report" not in wpost
    assert "FR #6142" in wpost
