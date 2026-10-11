"""Hostile pins for MRB #3944 / FR #3943 subprocess UTF-8 text capture."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
SKILL = (
    ROOT
    / "bob"
    / ".grok"
    / "skills"
    / "bobiverse-bob-troubleshooting"
    / "SKILL.md"
)

NEEDLE = (
    "Crash hook: `UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d` "
    "in `subprocess._readerthread`"
)

# Product EAR list plus adjacent same-class modules patched in #3944.
MODULES = (
    "bob_recycle.py",
    "bobstat.py",
    "protect.py",
    "agent_control.py",
    "talk_seat_pid.py",
    "prior_irc.py",
    "crash_report.py",
    "live_tree_guard.py",
    "gh_filer.py",
    "jeeves_maintenance.py",
)


def _text_true_calls_missing_encoding(src: str) -> list[int]:
    lines = src.splitlines()
    bad: list[int] = []
    for i, line in enumerate(lines):
        if "text=True" not in line and "universal_newlines=True" not in line:
            continue
        window = "\n".join(lines[max(0, i - 12) : i + 5])
        if re.search(r'encoding\s*=\s*[\'"]utf-8[\'"]', window):
            continue
        bad.append(i + 1)
    return bad


def test_mrb3944_troubleshooting_fr3943_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "SKILL.md must be UTF-8 no BOM"
    text = raw.decode("utf-8")
    assert "\ufffd" not in text
    assert NEEDLE in text
    assert "subprocess_utf8.py" in text
    assert "encoding=\"utf-8\"" in text or "encoding='utf-8'" in text or "encoding=\"utf-8\", errors=\"replace\"" in text


def test_mrb3944_subprocess_utf8_helper():
    import sys

    sys.path.insert(0, str(SCRIPTS))
    import subprocess_utf8

    assert subprocess_utf8.TEXT["text"] is True
    assert subprocess_utf8.TEXT["encoding"] == "utf-8"
    assert subprocess_utf8.TEXT["errors"] == "replace"


@pytest.mark.parametrize("name", MODULES)
def test_mrb3944_module_text_true_uses_utf8(name: str):
    path = SCRIPTS / name
    assert path.is_file(), name
    src = path.read_text(encoding="utf-8")
    if "text=True" not in src and "universal_newlines=True" not in src:
        pytest.skip(f"{name} has no text=True")
    bad = _text_true_calls_missing_encoding(src)
    assert bad == [], f"{name}: text=True without encoding='utf-8' at lines {bad}"
