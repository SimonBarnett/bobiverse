"""MRB #5313: park-only Airc LEGION FR vision pack (fix: validator Shape + mocks)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AIRC = Path(__file__).resolve().parents[1]
FR = AIRC / "docs" / "feature-request-airc-legion-2026-10-31.md"
MOCKS = AIRC / "docs" / "mocks" / "legion"
VALIDATOR = AIRC.parent / "jeeves" / "tools" / "validate-vision-pack.py"


def _text() -> str:
    return FR.read_text(encoding="utf-8")


def test_fr_utf8_no_bom_no_emdash():
    raw = FR.read_bytes()
    assert FR.is_file()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "\ufffd" not in text
    assert "\u2014" not in text


def test_shape_primary_own_line():
    in_shape = False
    found = False
    for line in _text().splitlines():
        if line.strip() == "## Shape":
            in_shape = True
            continue
        if in_shape and line.startswith("## "):
            break
        if in_shape and line.strip() in ("Primary: **service**", "Primary: service"):
            found = True
    assert found, "validator needs Primary on its own line"


def test_fr_locked_legion_isolation():
    text = _text()
    assert "LEGION" in text
    assert "airc_network_installer" in text
    assert "isolated" in text.lower()
    assert "PriorityAirc/LegionAdmin" in text
    assert "no `--force`" in text or "no --force" in text
    for sid in ("S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        assert f"| {sid} |" in text, sid
    for n in ("#5308", "#5309", "#5310", "#5311", "#5312"):
        assert n in text
    assert "Closes #5308" not in text
    assert "password=" not in text.lower()
    assert "airc/docs/mocks/legion" in text
    assert "\x07irc" not in text


def test_mocks_and_validate():
    for name, needle in (
        ("home.html", 'data-state="home"'),
        ("empty.html", 'data-state="empty"'),
        ("error.html", 'data-state="error"'),
    ):
        p = MOCKS / name
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), name
        assert needle in raw.decode("utf-8"), name
    r = subprocess.run(
        [sys.executable, str(VALIDATOR), str(FR), "--mocks-dir", str(MOCKS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
