"""Registry + !register parse for bobiverse."""

from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
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


def test_recycle_jeeves_token():
    sys.path.insert(0, str(ROOT / "scripts"))
    import bob_recycle

    assert bob_recycle.resolve_recycle_machine("jeeves") == "jeeves"
    assert bob_recycle.parse_recycle_query("!recycle jeeves") == ("run", "jeeves")


def test_airc_console_nick_shape():
    sys.path.insert(0, str(ROOT / "scripts"))
    import airc_console as ac

    assert ac.machine_console_nick("marchhare") == "marchhare_console"
    assert ac.machine_console_nick("ionos").endswith("_console")
