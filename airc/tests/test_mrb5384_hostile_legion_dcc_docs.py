"""MRB #5384 hostile pin: LEGION DCC log schema + remote-control docs."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg


def test_mrb5384_legion_log_always_has_failures_key():
    log = lg.build_legion_log(target="box", failures=[{"host": "box", "error": "x"}])
    assert "failures" in log
    assert log["failure_count"] == 1
    raw = lg.legion_log_bytes(log).decode("utf-8").lower()
    assert "password" not in raw


def test_mrb5384_remote_control_documents_legion():
    doc = Path(__file__).resolve().parents[1] / "docs" / "airc-remote-control.md"
    text = doc.read_text(encoding="utf-8")
    assert "LEGION" in text
    assert "5311" in text or "DCC" in text
