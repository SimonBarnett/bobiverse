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
        "harvest hold",  # FR #1611 / MRB #1619 nits: align with bob-worker BoredEmitter
    ):
        assert needle in lower, f"VISION.md must mention {needle!r}"


def test_bob_vision_utf8_no_bom():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "VISION.md must be UTF-8 without BOM"
    VISION.read_text(encoding="utf-8")  # round-trip


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


def test_bob_vision_s2_agents_submenu_fr6226():
    """FR #6226: S2 + Architecture document Agents submenu (post-#6216 / #6222)."""
    text = VISION.read_text(encoding="utf-8")
    assert "Tray **Agent**" not in text
    assert "Tray **Agents**" in text
    for name in ("Automatic", "Grok", "Cursor", "OpenCode"):
        assert name in text, name
    arch = text[text.index("## Architecture") :]
    # Singular Architecture menu row must not remain.
    assert "Agents" in arch.split("Plan", 1)[0]
    assert "Plan" in arch
    # Reject leftover singular Agent menu label (space-padded as in the old tree).
    assert " Agent  " not in arch.replace("Agents", "X")
    assert "one console = one agent" in text
