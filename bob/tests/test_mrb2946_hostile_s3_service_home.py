"""Hostile pins for MRB #2946 / FR #2943: S3 departure uses service ear home.

VISION S3 requires Channel PRIVMSG departure announce. Live LocalSystem ircBob
drains InstallRoot\\home — not %USERPROFILE%\\.bobiverse (UAT undrained orphan).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
EAR = ROOT / "bob" / "scripts" / "Restart-BobEar.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-ear.md"
VISION = ROOT / "common" / "docs" / "vision.md"


def _t(p: Path) -> str:
    assert p.is_file(), p
    text = p.read_text(encoding="utf-8-sig")
    assert not text.startswith("\ufeff")
    assert text.endswith("\n")
    return text


def test_mrb2946_vision_s3_departure_announce_contiguous():
    text = _t(VISION)
    assert "departure announce" in text
    assert "Recycle path" in text
    # Contiguous S3 row still names Channel PRIVMSG + Running.
    assert "Channel PRIVMSG" in text
    assert "Get-Service ircBob" in text or "ircBob" in text


def test_mrb2946_helper_prefers_installroot_home_over_profile():
    text = _t(COMMON)
    fn = text[text.find("function Get-BobiverseEarServiceHome") :]
    assert "function Get-BobiverseEarServiceHome" in fn
    window = fn[:2200]
    assert "BOB_EAR_HOME" in window
    assert "InstallRoot" in window
    assert "AppDirectory" in window
    # Helper body must resolve home under install/service root (no profile Join-Path).
    assert "Join-Path" in window and "home" in window
    assert "Join-Path $env:USERPROFILE" not in window
    assert "Join-Path $env:USERPROFILE '.bobiverse'" not in window


def test_mrb2946_restart_bob_ear_announce_drain_service_home():
    text = _t(EAR)
    assert "Get-BobiverseEarServiceHome" in text
    assert "depart-request.txt" in text
    assert "outbox.txt" in text
    assert "PRIVMSG #bobiverse" in text
    assert "logging off IRC" in text
    assert "DrainTimeoutSec" in text or "deadline" in text
    # Primary home is helper / InstallRoot\\home — not profile Join-Path alone.
    assert "Join-Path $InstallRoot 'home'" in text or 'Join-Path $InstallRoot "home"' in text
    assert "Join-Path $env:USERPROFILE '.bobiverse'" not in text


def test_mrb2946_force_new_block_uses_helper_before_profile_fallback():
    text = _t(FLEET)
    idx = text.find("$ForceNew -and $hits.Count")
    assert idx >= 0
    block = text[idx : idx + 6500]
    assert "Get-BobiverseEarServiceHome" in block
    assert "Join-Path $RepoRoot 'home'" in block or 'Join-Path $RepoRoot "home"' in block
    # Executable assignment to profile home is last resort after helper/install attempts.
    i_helper = block.find("Get-BobiverseEarServiceHome")
    i_assign = block.find("Join-Path $env:USERPROFILE '.bobiverse'")
    assert i_helper >= 0
    assert i_assign > i_helper
    assert "bob-ear.exe" in block or "ircBob" in block


def test_mrb2946_watch_logout_prefers_service_home():
    text = _t(WATCH)
    logout = text[text.find("function Request-BobTrayIrcLogout") :][:3500]
    assert "Get-BobiverseEarServiceHome" in logout
    assert "FR #2943" in logout
    i_helper = logout.find("Get-BobiverseEarServiceHome")
    i_assign = logout.find("Join-Path $env:USERPROFILE '.bobiverse'")
    assert i_helper >= 0
    assert i_assign > i_helper


def test_mrb2946_bob_ear_docs_note_service_home():
    text = _t(DOCS)
    assert "FR #2943" in text
    assert "Get-BobiverseEarServiceHome" in text
    assert "InstallRoot" in text and "home" in text
    assert "USERPROFILE" in text or ".bobiverse" in text
