"""MRB #6948 hostile pins for FR #6947 walrus-only chair."""
from __future__ import annotations

from pathlib import Path

import jeeves_chair_host as jch
from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
START = ROOT / "jeeves" / "scripts" / "Start-Jeeves.ps1"
IRC = ROOT / "common" / "scripts" / "irc_agent.py"
DOCS = ROOT / "jeeves" / "docs" / "jeeves-exe-self-heal.md"


def test_mrb6948_exit_code_and_no_delete_stray():
    assert jch.EXIT_WRONG_HOST == 4
    start = START.read_text(encoding="utf-8")
    assert "exit 4" in start
    assert "CHAIR_HOST_REFUSED" in start
    common = COMMON.read_text(encoding="utf-8")
    fn = common[common.index("function Disable-BobiverseStrayChairService") :]
    fn = fn[: fn.index("\nfunction ")]
    assert "StartupType Disabled" in fn or "Disabled" in fn
    assert "Stop-Service" in fn
    assert "Remove-BobiverseService" not in fn
    assert "sc.exe delete" not in fn.lower() and " sc delete" not in fn.lower()
    assert "not deleted" in fn.lower() or "never delete" in fn.lower() or "not delete" in fn.lower()


def test_mrb6948_chair_nick_abort_sets_no_reconnect():
    src = IRC.read_text(encoding="utf-8")
    block = src.split('if cmd in ("433", "432"):', 1)[1][:1200]
    assert "chair_nick_in_use_must_exit" in block
    assert "_no_reconnect" in block
    assert "chair_nick_taken_line" in block
    assert 'self._abort_gate("CHAIR_NICK_TAKEN")' in src
    # Chair branch must not fall into original_nick + "_l"
    chair_if = block.split("chair_nick_in_use_must_exit", 1)[1][:350]
    assert '_l"' not in chair_if and "+ \"_l\"" not in chair_if


def test_mrb6948_install_and_docs_walrus_only():
    inst = INSTALL.read_text(encoding="utf-8")
    assert "InstallChairService" in inst
    assert "Disable-BobiverseStrayChairService" in inst
    assert "--chair-host" not in inst
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "6947" in docs or "walrus" in docs.lower()
    assert not docs.startswith("\ufeff")
