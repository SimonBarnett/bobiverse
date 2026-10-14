"""FR #3943: bob-ear UnicodeDecodeError in subprocess._readerthread (cp1252 + byte 0x9d).

On Windows, ``text=True`` without ``encoding=`` uses locale cp1252 with strict
errors. Child stdout containing 0x9d (undefined in cp1252; common in UTF-8)
crashes the background reader thread and the crash hook files bob-ear.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# Modules on the bob-ear (irc_agent) import / call graph that use text subprocess.
EAR_TEXT_SUBPROCESS_MODULES = (
    "bob_recycle.py",
    "bobstat.py",
    "protect.py",
    "agent_control.py",
    "talk_seat_pid.py",
    "prior_irc.py",
    "crash_report.py",
    "live_tree_guard.py",
)


def test_fr3943_cp1252_rejects_0x9d():
    """Document the crash codec: cp1252 cannot decode 0x9d (strict)."""
    blob = b"ok\x9dmore"
    with pytest.raises(UnicodeDecodeError):
        blob.decode("cp1252")


def test_fr3943_utf8_replace_survives_0x9d():
    blob = b"ok\x9dmore"
    out = blob.decode("utf-8", errors="replace")
    assert "ok" in out and "more" in out


def test_fr3943_subprocess_utf8_helper_shape():
    import subprocess_utf8

    assert subprocess_utf8.TEXT["text"] is True
    assert subprocess_utf8.TEXT["encoding"] == "utf-8"
    assert subprocess_utf8.TEXT["errors"] == "replace"


def _text_true_calls_missing_encoding(src: str) -> list[int]:
    """Return 1-based line numbers of ``text=True`` lacking encoding= in the call window."""
    lines = src.splitlines()
    bad: list[int] = []
    for i, line in enumerate(lines):
        if "text=True" not in line and "universal_newlines=True" not in line:
            continue
        # Window: up to 12 lines back (kwargs) and 4 forward.
        window = "\n".join(lines[max(0, i - 12) : i + 5])
        if re.search(r'encoding\s*=\s*[\'"]utf-8[\'"]', window):
            continue
        bad.append(i + 1)
    return bad


@pytest.mark.parametrize("name", EAR_TEXT_SUBPROCESS_MODULES)
def test_fr3943_ear_module_text_true_uses_utf8(name: str):
    path = SCRIPTS / name
    assert path.is_file(), name
    src = path.read_text(encoding="utf-8")
    if "text=True" not in src and "universal_newlines=True" not in src:
        pytest.skip(f"{name} has no text=True")
    bad = _text_true_calls_missing_encoding(src)
    assert bad == [], f"{name}: text=True without encoding='utf-8' at lines {bad}"
