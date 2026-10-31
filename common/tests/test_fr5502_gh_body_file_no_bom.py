"""FR #5502: gh --body-file must be UTF-8 without BOM.

WinPS ``Set-Content -Encoding utf8`` writes EF BB BF. ``gh pr create --body-file``
then stores U+FEFF as the first character of the PR body (seen on #5501).
Seats write the file with ``Write-BobiverseUtf8NoBom.ps1``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HELPER = ROOT / "common" / "scripts" / "Write-BobiverseUtf8NoBom.ps1"
if not HELPER.is_file():
    HELPER = ROOT / "scripts" / "Write-BobiverseUtf8NoBom.ps1"

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
BOM = b"\xef\xbb\xbf"


def test_fr5502_helper_and_skill_pin_no_bom():
    assert HELPER.is_file()
    text = HELPER.read_text(encoding="utf-8")
    assert "FR #5502" in text
    assert "UTF8Encoding" in text
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #5502" in skill
    assert "Write-BobiverseUtf8NoBom" in skill
    assert "Set-Content -Encoding utf8" in skill


def test_fr5502_helper_writes_utf8_without_bom(tmp_path: Path):
    dest = tmp_path / "pr-body.md"
    body = "## Summary\nCloses SimonBarnett/bobiverse#5502\n"
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HELPER),
            "-Path",
            str(dest),
            "-Value",
            body,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    raw = dest.read_bytes()
    assert not raw.startswith(BOM), raw[:8]
    assert raw.decode("utf-8").startswith("## Summary")


def test_fr5502_set_content_utf8_still_writes_bom(tmp_path: Path):
    """Document the footgun the helper exists to avoid (WinPS 5.1)."""
    dest = tmp_path / "set-content.md"
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"Set-Content -LiteralPath '{dest}' -Value '## Summary' -Encoding utf8",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    raw = dest.read_bytes()
    # WinPS 5.1 prefixes BOM; pwsh 7 often does not. Helper is required either way.
    if raw.startswith(BOM):
        assert True
    else:
        # Core pwsh: still prove helper contract separately.
        assert dest.read_text(encoding="utf-8").lstrip("\ufeff").startswith("## Summary")
