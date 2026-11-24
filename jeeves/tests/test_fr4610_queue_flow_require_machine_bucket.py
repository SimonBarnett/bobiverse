"""FR #4610: queue_flow require_machine bucket matches offer gates (FR #4512)."""
from __future__ import annotations

from pathlib import Path
import sys

MONITOR = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MONITOR))

import queue_flow  # noqa: E402


def test_fr4610_gate_bucket_uses_needs_label_not_raw_stamp_or_body():
    """Bobiverse raw stamp / body pin alone are not a gate; needs-<machine> is."""
    stamped_only = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#4610a",
        "title": "stale stamp only",
        "labels": ["feature-request"],
        "require_machine": "ce-priority-dev1",
    }
    assert queue_flow._gate_bucket(stamped_only) == "ungated"

    body_only = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#4610b",
        "title": "IONOS pin",
        # FR #9637: body require_machine: alone must not gate.
        "body": "require_machine: ionos\n",
        "labels": ["feature-request"],
    }
    assert queue_flow._gate_bucket(body_only) == "ungated"

    labeled = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#4610c",
        "title": "walrus pin",
        "body": "require_machine: walrus\n",
        "labels": ["feature-request", "needs-walrus"],
    }
    assert queue_flow._gate_bucket(labeled) == "require_machine"
