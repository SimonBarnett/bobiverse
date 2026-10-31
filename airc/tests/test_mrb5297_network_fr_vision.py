"""MRB #5297: park-only Airc NETWORK diagnostic FR vision pack."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AIRC = Path(__file__).resolve().parents[1]
FR = AIRC / "docs" / "feature-request-airc-network-diagnostic-2026-10-31.md"
MOCKS = AIRC / "docs" / "mocks"
VALIDATOR = AIRC.parent / "jeeves" / "tools" / "validate-vision-pack.py"


def _text() -> str:
    return FR.read_text(encoding="utf-8")


def test_fr_utf8_no_bom():
    raw = FR.read_bytes()
    assert FR.is_file()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "\ufffd" not in raw.decode("utf-8")


def test_fr_locked_network_isolation_dcc():
    text = _text()
    assert "## Objective" in text and "## Success" in text
    assert "NETWORK" in text and "isolated" in text.lower()
    assert "DCC" in text
    assert "UPDATE" in text
    for sid in ("S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        assert f"| {sid} |" in text, sid
    # Living slices are Refs, never closed by the park PR
    assert "#5298" in text and "#5299" in text and "#5300" in text and "#5301" in text
    assert "Closes #5298" not in text
    assert "Closes #5299" not in text


def test_mocks_home_empty_error():
    for name, needle in (
        ("home.html", "data-state=\"home\""),
        ("empty.html", "data-state=\"empty\""),
        ("error.html", "data-state=\"error\""),
    ):
        p = MOCKS / name
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), name
        body = raw.decode("utf-8")
        assert needle in body, name


def test_validate_vision_pack_ok():
    r = subprocess.run(
        [sys.executable, str(VALIDATOR), str(FR), "--mocks-dir", str(MOCKS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
