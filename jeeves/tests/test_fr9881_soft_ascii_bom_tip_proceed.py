"""FR #9881: soft-only pytest-ascii-bom must not uniquely BLOCK tip when build-jeeves green."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")

SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_fr9881_rollup_soft_only_annotates_ascii_bom():
    runs = {
        "check_runs": [
            {
                "name": "build-jeeves",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "pytest-ascii-bom",
                "status": "completed",
                "conclusion": "failure",
            },
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "failure:pytest-ascii-bom"


def test_fr9881_rollup_hard_when_build_jeeves_also_red():
    runs = {
        "check_runs": [
            {
                "name": "build-jeeves",
                "status": "completed",
                "conclusion": "failure",
            },
            {
                "name": "pytest-ascii-bom",
                "status": "completed",
                "conclusion": "failure",
            },
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "failure"


def test_fr9881_tip_may_proceed_soft_when_build_jeeves_green():
    assert (
        mrb_merge_on_green.tip_may_proceed_soft_ascii_bom(
            "failure:pytest-ascii-bom",
            build_jeeves_green=True,
        )
        is True
    )
    assert (
        mrb_merge_on_green.tip_may_proceed_soft_ascii_bom(
            "failure:pytest-ascii-bom",
            build_jeeves_green=False,
        )
        is False
    )
    assert (
        mrb_merge_on_green.tip_may_proceed_soft_ascii_bom(
            "failure",
            build_jeeves_green=True,
        )
        is False
    )
    assert (
        mrb_merge_on_green.tip_may_proceed_soft_ascii_bom(
            "failure:build-jeeves",
            build_jeeves_green=True,
        )
        is False
    )


def test_fr9881_decide_merge_on_green_soft_waits_not_requeue_ci():
    decision = mrb_merge_on_green.decide_merge_on_green(
        pass_sha=SHA,
        current_sha=SHA,
        checks="failure:pytest-ascii-bom",
    )
    assert decision == "wait"
    hard = mrb_merge_on_green.decide_merge_on_green(
        pass_sha=SHA,
        current_sha=SHA,
        checks="failure",
    )
    assert hard == "requeue_ci"
    hard_named = mrb_merge_on_green.decide_merge_on_green(
        pass_sha=SHA,
        current_sha=SHA,
        checks="failure:build-jeeves",
    )
    assert hard_named == "requeue_ci"


def test_fr9881_fix_ci_skip_reason_soft_allow():
    assert (
        mrb_merge_on_green.fix_ci_skip_reason("failure:pytest-ascii-bom")
        == "soft-allow-ascii-bom"
    )
    assert mrb_merge_on_green.fix_ci_skip_reason("failure") is None
    assert mrb_merge_on_green.fix_ci_skip_reason("failure:build-jeeves") is None


def test_fr9881_ps1_ascii_check_hint_names_prefer_a_helpers(tmp_path: Path, capsys):
    bad = tmp_path / "bad.ps1"
    bad.write_bytes("Write-Host 'x\u2014y'\n".encode("utf-8"))
    import bobiverse_ps1_ascii as mod

    code = mod.main(["check", "--path", str(tmp_path)])
    assert code == 2
    out = capsys.readouterr().out
    assert "Write-BobiversePs1AsciiNoBom" in out or "bobiverse_ps1_ascii.py write" in out
    assert "9881" in out
