"""docs/mrb-3720: hostile pin FR-3715 fr70 SetInstallCmd aligned with FR #3685."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
FR70 = REPO / "common" / "tests" / "test_fr70_runinstall_msi_props.py"
MRB = REPO / "airc" / "tests" / "test_mrb3693_hostile_fr3685_cmd_fail.py"


def test_mrb3720_fr70_and_pack_share_cmd_call_wrap():
    pack = PACK.read_text(encoding="utf-8")
    fr70 = FR70.read_text(encoding="utf-8")
    mrb = MRB.read_text(encoding="utf-8")
    assert "&quot;[System64Folder]cmd.exe&quot; /d /c call" in pack
    assert "$installArgs" in pack
    assert 'Id="SetInstallCmd"' in pack or "SetInstallCmd" in pack
    assert "&quot;[System64Folder]cmd.exe&quot; /d /c call" in fr70
    assert "$installArgs" in fr70
    assert "test_mrb3693_fr70_pin_tracks_cmd_call_wrap" in mrb
