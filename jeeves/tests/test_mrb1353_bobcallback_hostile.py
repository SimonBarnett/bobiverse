"""Hostile MRB #1353: never re-register BobCallback as SYSTEM against Admin home."""
from __future__ import annotations

from pathlib import Path

JEEVES = Path(__file__).resolve().parents[1]
INSTALL = JEEVES / "scripts" / "Install-Jeeves.ps1"
REGISTER = JEEVES / "scripts" / "Register-BobCallbackTask.ps1"
START = JEEVES / "scripts" / "Start-Jeeves.ps1"


def test_register_refuses_system_runas_user():
    text = REGISTER.read_text(encoding="utf-8-sig")
    # Must actively refuse LocalSystem / SYSTEM / S-1-5-18, not only document the anti-pattern.
    assert "S-1-5-18" in text or "LocalSystem" in text
    assert "throw" in text.lower() or "throw " in text
    # Refuse path should mention SYSTEM / LocalSystem explicitly as blocked.
    lowered = text.lower()
    assert "refuse" in lowered or "must not" in lowered or "never" in lowered
    assert "system" in lowered


def test_install_forces_administrator_when_digest_is_admin_home():
    text = INSTALL.read_text(encoding="utf-8-sig")
    # LocalSystem MSI install must not pass $env:USERNAME blindly when home is Admin .bobiverse.
    assert "Administrator" in text
    assert (
        "Users\\Administrator\\.bobiverse" in text
        or "Users\\Administrator\\.bobiverse" in text.replace("/", "\\")
        or "adminDigest" in text
    )
    # Prefer an explicit RunAsUser = Administrator when digest is the Admin profile home
    # (or when Test-BobiverseIsLocalSystem), not only $env:USERNAME.
    assert "Test-BobiverseIsLocalSystem" in text
    assert (
        "RunAsUser = 'Administrator'" in text
        or 'RunAsUser = "Administrator"' in text
        or "RunAsUser='Administrator'" in text
        or '$cbRunAs = \'Administrator\'' in text
        or '$cbRunAs = "Administrator"' in text
        or "$cbRunAs = 'Administrator'" in text
    )


def test_start_jeeves_wedge_warn_when_running_without_listen():
    text = START.read_text(encoding="utf-8-sig")
    assert "Running but" in text or "not LISTENING" in text
    assert "FR #1316" in text
