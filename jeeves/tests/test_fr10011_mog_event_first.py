"""FR #10011: merge-on-green backup is hourly; workflow_run needs no REST."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import chair_health as ch  # noqa: E402


def test_fr10011_backup_is_hourly():
    assert ch.MERGE_ON_GREEN_S >= 3600
    text = (ROOT / "jeeves" / "docs" / "jeeves-commands.md").read_text(encoding="utf-8")
    assert "FR #10011" in text
    assert "workflow_run" in text
