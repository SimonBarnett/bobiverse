"""docs/mrb-6687: hostile pins for FR #6667 / PR #6687.

Shared-home busy pin clears ``BOBIVERSE_BUILD_SUITE``; suite mode keeps tmp
digest home (FR #6523) so !build isolation cannot hide seat work.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PIN = ROOT / "bob" / "tests" / "test_fr5890_recycleseat_busy.py"
REPORT = ROOT / "common" / "scripts" / "bobreport.py"


def test_mrb6687_shared_home_pin_clears_build_suite():
    t = PIN.read_text(encoding="utf-8-sig")
    assert "test_busy_check_uses_shared_digest_home" in t
    assert 'delenv("BOBIVERSE_BUILD_SUITE"' in t or "delenv('BOBIVERSE_BUILD_SUITE'" in t
    assert "test_busy_check_build_suite_keeps_tmp_digest_home" in t
    assert 'setenv("BOBIVERSE_BUILD_SUITE", "1")' in t or "setenv('BOBIVERSE_BUILD_SUITE', '1')" in t


def test_mrb6687_fleet_digest_home_keeps_tmp_under_build_suite():
    src = REPORT.read_text(encoding="utf-8-sig")
    i = src.index("def fleet_digest_home")
    body = src[i : i + 1200]
    assert "BOBIVERSE_BUILD_SUITE" in body
    assert "FR #6523" in body
    assert "_is_chair_home" in body
