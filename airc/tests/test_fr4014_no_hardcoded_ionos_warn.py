"""FR #4014: airc installer/console messages must not hardcode #ionos.

Walrus (client / #wonderland fallback) showed: console may join #win-... instead of #ionos.
Warnings must use the target machine id and name the real fallback (#wonderland).
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INSTALL_CONSOLE = (ROOT / "airc" / "scripts" / "Install-AircConsole.ps1").read_text(
    encoding="utf-8-sig"
)
START = (ROOT / "airc" / "scripts" / "Start-AircConsole.ps1").read_text(encoding="utf-8-sig")
SERVICE = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
OPS = (ROOT / "airc" / "docs" / "airc-ops.md").read_text(encoding="utf-8-sig")


def _message_files() -> list[Path]:
    scripts = ROOT / "airc" / "scripts"
    return [
        scripts / "Install-AircConsole.ps1",
        scripts / "Install-Airc.ps1",
        scripts / "Start-AircConsole.ps1",
        scripts / "Start-AircConsole-Fleet.ps1",
    ]


def test_fr4014_no_hardcoded_ionos_in_installer_console_messages():
    """Grep gate: installer/start scripts must not hardcode #ionos in user messages."""
    bad = []
    for path in _message_files():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            # Allow comments that discuss DIGEST fold / history only if they do not Write-Warning
            if "write-warning" in low or "write-host" in low or "write-error" in low:
                if "#ionos" in low or "instead of #ionos" in low:
                    bad.append(f"{path.name}:{i}:{line.strip()}")
                if "machineid ionos" in low.replace(" ", ""):
                    bad.append(f"{path.name}:{i}:{line.strip()}")
            # Any Write-Warning mentioning ionos as the expected shop is banned
            if "write-warning" in low and "ionos" in low:
                bad.append(f"{path.name}:{i}:{line.strip()}")
    assert bad == [], "hardcoded ionos in installer/console messages:\n" + "\n".join(bad)


def test_fr4014_install_warning_uses_machine_or_wonderland():
    assert "FR #4014" in INSTALL_CONSOLE or "wonderland" in INSTALL_CONSOLE.lower()
    assert "instead of #ionos" not in INSTALL_CONSOLE
    assert "#ionos" not in INSTALL_CONSOLE
    # Mentions wonderland fallback or dynamic shop
    assert "wonderland" in INSTALL_CONSOLE.lower() or "#{0}" in INSTALL_CONSOLE or "#$MachineId" in INSTALL_CONSOLE or "#${" in INSTALL_CONSOLE


def test_fr4014_start_warning_no_ionos_example():
    assert "instead of #ionos" not in START
    assert "#ionos" not in START
    assert "FR #4014" in START or "wonderland" in START.lower()


def test_fr4014_service_logs_unregistered_shop_wonderland():
    assert "is not registered" in SERVICE
    assert "joining" in SERVICE.lower() and "wonderland" in SERVICE.lower()
    # Dynamic shop channel in the message (shop_channel / self.shop_channel)
    assert "shop_channel" in SERVICE
    idx = SERVICE.find("is not registered")
    chunk = SERVICE[max(0, idx - 200) : idx + 200]
    assert "wonderland" in chunk.lower()
    assert "FR #4014" in SERVICE or "FR#4014" in SERVICE


def test_fr4014_ops_documents():
    assert "FR #4014" in OPS
