"""FR #1055: Install/Update pin NSSM AppExit 0=Restart for graceful quit."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_common_defines_appexit_helper():
    text = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8")
    assert "function Set-BobiverseNssmAppExitRestart" in text
    assert "AppExit', '0', 'Restart'" in text or 'AppExit", "0", "Restart"' in text or "AppExit', '0', 'Restart'" in text.replace('"', "'")


def test_install_jeeves_calls_appexit_helper():
    text = (ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1").read_text(encoding="utf-8")
    assert "Set-BobiverseNssmAppExitRestart" in text
    assert "FR #1055" in text


def test_install_bob_calls_appexit_helper():
    text = (ROOT / "bob" / "scripts" / "Install-Bob.ps1").read_text(encoding="utf-8")
    assert "Set-BobiverseNssmAppExitRestart" in text


def test_update_reasserts_appexit_after_msi():
    text = (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8")
    assert "Set-BobiverseNssmAppExitRestart" in text
    assert "post-upgrade-appexit-restart" in text