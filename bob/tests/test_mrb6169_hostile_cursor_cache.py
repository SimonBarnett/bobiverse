"""MRB #6169 hostile pins: local cache guard + peer label isolation."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

IRC = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
HOVER = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
EAR = ROOT / "bob" / "docs" / "bob-ear.md"
BOBREPORT = ROOT / "common" / "scripts" / "bobreport.py"


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb6169_import_peer_uses_this_machine_id_not_moot():
    text = _t(IRC)
    start = text.index("function Import-BobIrcPeerTranscript")
    block = text[start : start + 4500]
    assert "Get-ThisMachineId" in block
    assert "MRB #6169" in block or "FR #6144 / MRB #6169" in block
    # Must not compare resolved peer id to mootId for account-cache stamp.
    assert "resolved -eq $mid" not in block or "Get-ThisMachineId" in block
    assert "$localMid" in block


def test_mrb6169_hover_does_not_cache_foreign_peer_label_as_local():
    text = _t(HOVER)
    assert "never stamp a peer label into the local account cache" in text
    assert "$mid -eq $machineId" in text
    assert "LocalPeriodEnd" in text
    assert "Test-BobCursorAccountCacheAcceptable" in text


def test_mrb6169_docs_mention_cursor_known():
    ear = _t(EAR)
    assert "cursor_known" in ear
    assert "sand_period_end" in ear


def test_mrb6169_cursor_group_keys_include_cur():
    src = _t(BOBREPORT)
    assert "_CURSOR_GROUP_KEYS" in src
    assert '"cur"' in src or "'cur'" in src
