"""FR #3967: Bobiverse-Common.ps1 must not use the PS 5 type constructor on the airc path.

#3911 / FR #3904 introduced List[string] type-ctor calls in Get-BobiverseErgoPasswordPath
and Ensure-BobiverseBobNickServPassword. airc client path dotsources Bobiverse-Common and
must run on Windows PowerShell 4.0 (FR #3684 / MRB #3688). Use New-Object instead.
"""
from __future__ import annotations

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
# Literal needle used by test_mrb3688 (keep in sync; do not write it into Common comments).
_PS5_CTOR = "::" + "new("


def test_fr3967_common_has_no_type_new_operator():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert _PS5_CTOR not in text, "replace PS5 type ctor with New-Object for PS 4.0 (FR #3967)"


def test_fr3967_password_helpers_use_new_object_list():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "Get-BobiverseErgoPasswordPath" in text
    assert "Ensure-BobiverseBobNickServPassword" in text
    assert "New-Object 'System.Collections.Generic.List[string]'" in text
    assert "FR #3967" in text
