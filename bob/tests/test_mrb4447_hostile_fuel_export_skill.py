"""MRB #4447 hostile pin: fuel-export lesson lives in bob-worker, not harvest."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
HARVEST = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
NEEDLE = (
    "Get-BobAgentFuel must call only functions listed in BobBridge FunctionsToExport "
    "and Export-ModuleMember. A CommandNotFound inside an empty catch leaves "
    "cursor.high and cursor.low null, so select_agent skips Cursor when Grok is exhausted"
)


def test_mrb4447_fuel_export_lesson_in_worker_skill():
    raw = WORKER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "<<<<<<<" not in text


def test_mrb4447_fuel_export_lesson_not_in_harvest_book():
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert NEEDLE not in raw.decode("utf-8")
