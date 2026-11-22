"""FR #8765: ASCII-safe BOM-less *.ps1 write + scan helpers (pytest-ascii-bom)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

ROOT = REPO
HELPER_PY = ROOT / "common" / "scripts" / "bobiverse_ps1_ascii.py"
HELPER_PS1 = ROOT / "common" / "scripts" / "Write-BobiversePs1AsciiNoBom.ps1"
ASSERT_PS1 = ROOT / "common" / "scripts" / "Assert-BobiverseChangedPs1Ascii.ps1"
FLEET = ROOT / "common" / "scripts" / "Update-BobFleet.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def test_fr8765_helpers_ship():
    assert HELPER_PY.is_file(), "bobiverse_ps1_ascii.py required"
    assert HELPER_PS1.is_file(), "Write-BobiversePs1AsciiNoBom.ps1 required"
    assert ASSERT_PS1.is_file(), "Assert-BobiverseChangedPs1Ascii.ps1 required"
    text = HELPER_PY.read_text(encoding="utf-8")
    assert "sanitize_ps1_text" in text
    assert "write_ps1_ascii_nobom" in text
    assert "scan_ps1_paths" in text
    assert "\\u2014" in text or "\u2014" in text or "2014" in text


def test_fr8765_sanitize_replaces_em_dash_and_smart_quotes():
    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bobiverse_ps1_ascii as mod  # noqa: WPS433

    raw = "hello\u2014world \u2018x\u2019 \u201cY\u201d \u2013 z\u2026"
    out = mod.sanitize_ps1_text(raw)
    assert "\u2014" not in out
    assert "\u2013" not in out
    assert "\u2018" not in out and "\u2019" not in out
    assert "\u201c" not in out and "\u201d" not in out
    assert "\u2026" not in out
    assert "hello-world" in out
    assert "'x'" in out
    assert '"Y"' in out
    assert "..." in out
    assert all(ord(ch) < 128 for ch in out)


def test_fr8765_write_ps1_ascii_nobom_fail_closed(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bobiverse_ps1_ascii as mod  # noqa: WPS433

    path = tmp_path / "sample.ps1"
    mod.write_ps1_ascii_nobom(path, "Write-Host 'ok\u2014done'\n")
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\xe2\x80\x94" not in raw  # UTF-8 em dash
    assert b"ok-done" in raw

    # Unsanitizable leftover (e.g. CJK) must refuse.
    with pytest.raises(ValueError, match="non-ASCII"):
        mod.write_ps1_ascii_nobom(path, "hello\u4e16\u754c\n")


def test_fr8765_scan_flags_bomless_non_ascii(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bobiverse_ps1_ascii as mod  # noqa: WPS433

    good = tmp_path / "good.ps1"
    bad = tmp_path / "bad.ps1"
    good.write_bytes(b"Write-Host 'ok'\n")
    bad.write_bytes("Write-Host 'bad\u2014'\n".encode("utf-8"))
    problems = mod.scan_ps1_paths([good, bad])
    assert problems
    assert any("bad.ps1" in p for p in problems)
    assert not any("good.ps1" in p for p in problems)


def test_fr8765_cli_check_exits_nonzero_on_bad(tmp_path: Path):
    bad = tmp_path / "bad.ps1"
    bad.write_bytes("x\u2014y\n".encode("utf-8"))
    proc = subprocess.run(
        [sys.executable, str(HELPER_PY), "check", "--path", str(bad)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "bad.ps1" in (proc.stdout + proc.stderr)


def test_fr8765_main_fleet_and_pack_are_clean():
    """Regression pins for the two shapes named in FR #8765."""
    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bobiverse_ps1_ascii as mod  # noqa: WPS433

    assert FLEET.is_file() and PACK.is_file()
    assert not mod.scan_ps1_paths([FLEET, PACK])
