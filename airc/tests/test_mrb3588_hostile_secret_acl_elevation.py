"""MRB #3588 hostile pins for FR #3583 secret ACL elevation check."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

FR3288 = ROOT / "airc/tests/test_fr3288_secret_acl.py"


def _embed() -> str:
    t = FR3288.read_text(encoding="utf-8")
    start = t.find("$denied = $false")
    end = t.find("Write-Output 'ACL_OK'")
    assert start >= 0 and end > start
    return t[start:end]


def test_mrb3588_embed_uses_isinrole_not_groups_high_il():
    embed = _embed()
    assert "IsInRole" in embed
    assert "WindowsBuiltInRole" in embed
    assert "Administrator" in embed
    assert "$id.Groups" not in embed
    assert "S-1-16-12288" not in embed
    assert "READ_OK_ELEVATED" in embed or "READ_OK_ELEVATED" in FR3288.read_text(encoding="utf-8")
    assert "READ_DENIED" in FR3288.read_text(encoding="utf-8")


def test_mrb3588_fr3583_source_pin_present():
    t = FR3288.read_text(encoding="utf-8")
    assert "FR #3583" in t
    assert "test_fr3583_elevation_check_uses_isinrole_not_groups_integrity" in t
