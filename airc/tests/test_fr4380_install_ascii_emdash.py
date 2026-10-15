"""FR #4380: Install-Airc*.ps1 must stay ASCII after FR #3900; mrb3869 pin tracks mint-marker."""
from __future__ import annotations

from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
MRB3869 = ROOT / "airc" / "tests" / "test_mrb3869_hostile_upgrade_sasl.py"


def test_fr4380_install_scripts_ascii_no_emdash():
    for path in (INSTALL, INSTALL_CONSOLE):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM on {path.name}"
        assert all(b < 128 for b in raw), f"non-ASCII in {path.name}"
        text = raw.decode("ascii")
        assert "\u2014" not in text
        assert "—" not in text


def test_fr4380_mrb3869_pin_matches_install_mint_marker():
    svc = SERVICE.read_text(encoding="utf-8")
    assert "install_minted" in svc
    assert "(not pw_existed) or install_minted" in svc
    pin = MRB3869.read_text(encoding="utf-8")
    assert "(not pw_existed) or install_minted" in pin
    assert "_nickserv_pw_minted = bool(self.nickserv_password) and not pw_existed" not in pin
