"""FR #4610: queue_flow require_machine bucket matches offer gates (FR #4512)."""
from __future__ import annotations

from pathlib import Path
import sys

MONITOR = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MONITOR))

import queue_flow  # noqa: E402


def test_fr4610_gate_bucket_uses_dedicated_body_pin_not_raw_stamp():
    """Bobiverse raw stamp alone is not a gate; dedicated body pin is."""
    stamped_only = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#4610a",
        "title": "stale stamp only",
        "labels": ["feature-request"],
        "require_machine": "ce-priority-dev1",
    }
    assert queue_flow._gate_bucket(stamped_only) == "ungated"

    dedicated = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#4610b",
        "title": "DEV1 pin",
        "body": "require_machine: ce-priority-dev1\n",
        "labels": ["feature-request"],
    }
    assert queue_flow._gate_bucket(dedicated) == "require_machine"
