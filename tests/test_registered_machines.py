"""Registry + !register parse for bobiverse."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import registered_machines as rm  # noqa: E402


def test_parse_register_command():
    assert rm.parse_register_command("!register machineA") == "machinea"
    assert rm.parse_register_command("!register #ionos") == "ionos"
    assert rm.parse_register_command("!recycle ionos") is None


def test_registry_roundtrip(tmp_path: Path):
    assert rm.add_registered(tmp_path, "MarchHare") == "marchhare"
    assert rm.is_registered(tmp_path, "marchhare")
    assert rm.load_registered(tmp_path) == {"marchhare"}
    assert rm.bob_nick_for_machine("marchhare") == "Bob-marchhare"
    assert rm.machine_from_bob_nick("Bob-marchhare") == "marchhare"
    assert rm.machine_from_bob_nick("bob-ionos") == "ionos"
