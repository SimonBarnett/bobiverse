"""FR #6103: after !recycleseat heal, do not file stall:bored-latency as an FR."""
from __future__ import annotations

from pathlib import Path

import chair_health
import stall_detectors as sd


def test_fr6103_healed_nicks_dropped_from_filer():
    now = 100_000.0
    found = sd.detect_bored_latency(
        {
            "now": now,
            "idle": {"flamingo-35004", "flamingo-47616"},
            "last_bored": {
                "flamingo-35004": now - 441,
                "flamingo-47616": now - 441,
            },
        }
    )
    assert {x["key"] for x in found} == {"flamingo-35004", "flamingo-47616"}
    kept = chair_health.drop_healed_bored_findings(
        found,
        ["bored-latency recycleseat=flamingo-35004 id=abc lag_s=441"],
    )
    assert [x["key"] for x in kept] == ["flamingo-47616"]


def test_fr6103_stall_scan_filters_healed_before_filer():
    src = (
        Path(__file__).resolve().parents[2] / "common" / "scripts" / "chair_health.py"
    ).read_text(encoding="utf-8")
    scan = src[src.find("def _stall_scan") :]
    assert "heal_bored_latency" in scan
    assert "drop_healed_bored_findings" in scan
    assert scan.find("drop_healed_bored_findings") < scan.find("apply_findings")
