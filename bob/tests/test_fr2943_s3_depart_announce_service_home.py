"""FR #2943: S3 recycle departure announce must target the service ear home.

VISION S3: Systray Restart / Restart-BobEar restart ircBob with departure announce.
Live ear (LocalSystem via Start-Bob) drains InstallRoot\\home\\outbox.txt — not
%USERPROFILE%\\.bobiverse\\outbox.txt.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
EAR = ROOT / "bob" / "scripts" / "Restart-BobEar.ps1"
# Composed/install path may be bob/scripts; source tray tools:
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
VISION = ROOT / "common" / "docs" / "vision.md"


def _t(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_vision_s3_requires_departure_announce():
    text = _t(VISION)
    assert "S3" in text
    assert "departure announce" in text.lower() or "Recycle path" in text


def test_common_exposes_ear_service_home_helper():
    text = _t(COMMON)
    assert "function Get-BobiverseEarServiceHome" in text
    assert "AppDirectory" in text
    assert "Join-Path" in text and "home" in text
    # Must not hard-require profile .bobiverse as the only home.
    assert "BOB_EAR_HOME" in text or "InstallRoot" in text


def test_restart_bob_ear_writes_depart_to_service_home():
    text = _t(EAR)
    assert "depart-request" in text
    assert "Restart-Service" in text
    assert "Get-BobiverseEarServiceHome" in text or "Join-Path" in text and "home" in text
    # Hostile: must not be the sole path Join-Path $env:USERPROFILE '.bobiverse' for the flag.
    assert "USERPROFILE" not in text or "Get-BobiverseEarServiceHome" in text
    # Prefer outbox announce + drain aligned with Watch-BobTray (FR acceptance).
    assert "outbox.txt" in text
    assert "logging off IRC" in text or "PRIVMSG #bobiverse" in text


def test_force_new_announce_uses_service_home_not_only_profile():
    text = _t(FLEET)
    assert "ForceNew" in text
    assert "logging off IRC" in text
    idx = text.find("$ForceNew -and $hits.Count")
    if idx < 0:
        idx = text.find("ForceNew")
    block = text[idx : idx + 5500]
    assert "outbox.txt" in block
    assert "Get-BobiverseEarServiceHome" in block
    assert "Join-Path $RepoRoot 'home'" in block or 'Join-Path $RepoRoot "home"' in block


def test_watch_tray_restart_logout_prefers_service_home():
    text = _t(WATCH)
    assert "function Write-BobTrayIrcDepartureAnnounce" in text
    assert "function Request-BobTrayIrcLogout" in text
    # Restart logout must be able to target ear service home.
    logout = text[text.find("function Request-BobTrayIrcLogout") :][:2500]
    assert "Get-BobiverseEarServiceHome" in logout or "home" in logout.lower()
