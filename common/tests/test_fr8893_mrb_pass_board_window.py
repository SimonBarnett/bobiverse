"""FR #8893: a long MRB board still counts as PASS."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_gate = importlib.import_module("mrb_merge_gate")


def _comment(body: str) -> dict:
    return {"author_association": "NONE", "body": body, "created_at": "2026-11-22T00:00:00Z"}


def test_fr8893_long_board_before_verdict_is_pass():
    filler = "Vision quote. " * 400
    assert len(filler) > 4000
    body = "## MRB board\n\n" + filler + "\n\n**Verdict:** PASS\n"
    assert mrb_merge_gate.MRB_PASS_BOARD_RE.search(body)
    assert mrb_merge_gate.find_mrb_pass_board([_comment(body)])


def test_fr8893_fail_and_unheaded_pass_do_not_count():
    fail = "## MRB board\n\n" + ("x" * 500) + "\n**Verdict:** FAIL\n"
    loose = ("y" * 500) + "\n**Verdict:** PASS\n"
    assert mrb_merge_gate.find_mrb_pass_board([_comment(fail), _comment(loose)]) is None
