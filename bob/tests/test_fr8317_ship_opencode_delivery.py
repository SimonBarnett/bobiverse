"""FR #8317: opencode_delivery must ship beside frozen bob-worker."""
from __future__ import annotations

from pathlib import Path

import worker_shipped_scripts as ship

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "bob_worker.py"
BOB_SCRIPTS = ROOT / "scripts"


def test_fr8317_opencode_delivery_in_shipped_scripts():
    names = ship.shipped_script_names(WORKER, BOB_SCRIPTS)
    assert "opencode_delivery.py" in names
    assert "opencode_seat_contract.py" in names


def test_fr8317_copy_includes_opencode_delivery(tmp_path: Path):
    dest = tmp_path / "scripts"
    copied = ship.copy_by_path_scripts(WORKER, BOB_SCRIPTS, dest)
    assert "opencode_delivery.py" in copied
    assert (dest / "opencode_delivery.py").is_file()
    assert (dest / "opencode_seat_contract.py").is_file()
