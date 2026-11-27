"""FR #10063: !copilot on|off gates a new Copilot handoff."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import focus_ignore as fi  # noqa: E402


def test_off_suppresses_handoff_and_on_allows_it(tmp_path: Path):
    assert fi.copilot_handoff_allowed(tmp_path) is True
    assert fi.dispatch(tmp_path, "simon", "simon", "!copilot", ops=True) == ["copilot: on"]
    assert fi.dispatch(tmp_path, "mallory", None, "!copilot off")[0].startswith("copilot: denied")
    assert fi.copilot_handoff_allowed(tmp_path) is True
    assert fi.dispatch(tmp_path, "simon", "simon", "!copilot off", ops=True) == ["copilot: off"]
    assert fi.copilot_handoff_allowed(tmp_path) is False
    assert fi.dispatch(tmp_path, "anyone", None, "!copilot") == ["copilot: off"]
    assert fi.dispatch(tmp_path, "simon", "simon", "!copilot on", ops=True) == ["copilot: on"]
    assert fi.copilot_handoff_allowed(tmp_path) is True
