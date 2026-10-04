"""FR #1615: bob product VISION.md exists for MRB/UAT vision-first judgement."""
from __future__ import annotations

from pathlib import Path

BOB_ROOT = Path(__file__).resolve().parents[1]
VISION = BOB_ROOT / "VISION.md"


def test_bob_vision_md_exists():
    assert VISION.is_file(), f"missing {VISION} (FR #1615)"


def test_bob_vision_has_required_sections():
    text = VISION.read_text(encoding="utf-8")
    for heading in ("## Objective", "## Success", "## Shape", "## Architecture"):
        assert heading in text, f"missing {heading}"
    # FR #1615 required product surfaces
    lower = text.lower()
    for needle in (
        "inject",
        "one window",
        "shop",
        "cast iron",
        "harvest",
        "!bored",
        "relay",
    ):
        assert needle in lower, f"VISION.md must mention {needle!r}"


def test_bob_vision_pack_validates():
    import subprocess
    import sys

    validator = BOB_ROOT / "agents" / "plan" / "tools" / "validate-vision-pack.py"
    mocks = BOB_ROOT / "mocks"
    assert validator.is_file()
    r = subprocess.run(
        [sys.executable, str(validator), str(VISION), "--mocks-dir", str(mocks)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr