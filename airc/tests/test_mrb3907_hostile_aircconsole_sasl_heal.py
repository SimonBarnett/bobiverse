"""MRB #3907 hostile pins for FR #3900 AircConsole identity / SASL 904 heal.

After product merge #3907:
- Install-Airc reads legacy AircConsole AppParameters before mint
- Migrates console.password when dest empty
- airc_console_service one-shot legacy heal on 904 then reconnect
- Troubleshooting + airc-ops document the upgrade gap
"""
from __future__ import annotations

from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PRODUCT_PIN = ROOT / "airc" / "tests" / "test_fr3900_aircconsole_sasl_heal.py"


def test_mrb3907_install_legacy_aircconsole_before_mint_contiguous():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3900" in text
    assert "prior identity from legacy AircConsole" in text
    assert text.index("ServiceName 'Airc'") < text.index("ServiceName 'AircConsole'")
    assert "migrated console.password from" in text
    assert "Get-Service -Name 'AircConsole'" in text or "ServiceName 'AircConsole'" in text

    console = INSTALL_CONSOLE.read_text(encoding="utf-8-sig")
    assert "FR #3900" in console
    assert "preserving identity from legacy AircConsole" in console


def test_mrb3907_service_904_heal_reconnect_contiguous():
    text = SERVICE.read_text(encoding="utf-8")
    assert "def _try_heal_console_password_from_legacy" in text
    assert "def _legacy_console_password_paths" in text
    assert "_fr3900_heal_attempted" in text
    assert 'cmd == "904" and self._try_heal_console_password_from_legacy()' in text
    assert "FR #3900 healed console.password from legacy" in text
    assert "self._force_reconnect = True" in text


def test_mrb3907_docs_skill_and_product_pin():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3900" in skill
    assert "AircConsole" in skill
    assert "SAPASSWD" in skill
    assert "FR #3899" in skill  # keep both upgrade rows after behind-main fold
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")

    ops = OPS.read_text(encoding="utf-8")
    assert "FR #3900" in ops
    assert "AircConsole" in ops
    assert not OPS.read_bytes().startswith(b"\xef\xbb\xbf")

    assert PRODUCT_PIN.is_file()
