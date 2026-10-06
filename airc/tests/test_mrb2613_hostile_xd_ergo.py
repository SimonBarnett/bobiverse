"""MRB #2613 hostile: fr77 no-Ergo gate must use $xd array (FR #2611).

Product PR #2613 updated the stale literal ``/XD ergo`` assert after FR #2563
moved robocopy excludes into ``$xd = @('ergo', ...)`` + foreach /XD.
These gates lock the product exclude and the fr77 test contract.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

UPD = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
# Flat install / airc tests also resolve scripts/ via repo_layout ROOT/scripts.
UPD_FLAT = ROOT / "scripts" / "Update-BobiverseService.ps1"
FR77 = ROOT / "airc" / "tests" / "test_fr77_update_detached.py"
HARVEST = ROOT / "common" / "docs" / "skill-harvest-log.md"


def _upd_text() -> str:
    for p in (UPD, UPD_FLAT):
        if p.is_file():
            return p.read_text(encoding="utf-8-sig")
    raise AssertionError("Update-BobiverseService.ps1 missing")


def test_mrb2613_product_xd_includes_ergo_and_foreach_xd():
    t = _upd_text()
    xd_m = re.search(r"\$xd\s*=\s*@\(([^)]*)\)", t)
    assert xd_m is not None
    assert "'ergo'" in xd_m.group(1)
    assert re.search(r"foreach\s*\(\s*\$d\s+in\s+\$xd\s*\)", t)
    assert "/XD" in t
    assert "SkipErgo" in t


def test_mrb2613_fr77_gate_asserts_xd_array_not_only_literal():
    t = FR77.read_text(encoding="utf-8-sig")
    body = t[t.find("def test_updater_script_check_has_no_msiexec_and_airc_identity_hooks") :]
    body = body[: body.find("\ndef ", 1)]
    assert "2611" in body or "2563" in body or "$xd" in body
    assert "re.search" in body and "$xd" in body
    assert "'ergo'" in body
    # Must not rely solely on the pre-#2563 literal as the only ergo gate.
    assert 'assert "/XD ergo" in t' not in body


def test_mrb2613_harvest_log_marks_lesson():
    log = HARVEST.read_text(encoding="utf-8-sig")
    assert "2611" in log or "2613" in log
    assert "$xd" in log or "xd array" in log.lower()
