"""FR #7302: WinError 448 on WinGet Links opencode.exe must not crash the worker."""
from __future__ import annotations

from pathlib import Path

import pytest

import bob.scripts.bob_worker as bw


def _oserror_448(path: Path) -> OSError:
    err = OSError(
        448,
        "The path cannot be traversed because it contains an untrusted mount point",
    )
    err.winerror = 448
    err.filename = str(path)
    return err


def test_fr7302_untrusted_mount_helper():
    assert bw._is_untrusted_mount_oserror(_oserror_448(Path("x")))
    assert not bw._is_untrusted_mount_oserror(OSError(2, "not found"))
    other = OSError("untrusted mount point: WinGet")
    assert bw._is_untrusted_mount_oserror(other)


@pytest.mark.parametrize("raise_on_which", [False, True])
def test_fr7302_winget_link_448_uses_programs_path(tmp_path, monkeypatch, raise_on_which):
    la = tmp_path / "la"
    pkg = la / "Programs" / "opencode"
    pkg.mkdir(parents=True)
    real = pkg / "opencode.exe"
    real.write_bytes(b"MZ")
    link = la / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    link.parent.mkdir(parents=True)
    link.write_bytes(b"MZ")

    orig = Path.is_file

    def fake_is_file(self):
        s = str(self).replace("/", "\\")
        if "WinGet" in s and "Links" in s:
            raise _oserror_448(self)
        return orig(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)

    def which(_name):
        if raise_on_which:
            raise _oserror_448(link)
        return None

    reasons = []
    found = bw.resolve_opencode_cmd(
        env={"LOCALAPPDATA": str(la)},
        which=which,
        reasons=reasons,
    )
    assert found == str(real)
    assert any("448" in r or "untrusted" in r.lower() for r in reasons)


def test_fr7302_winget_link_448_without_fallback_is_none(tmp_path, monkeypatch):
    la = tmp_path / "la"
    link = la / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    link.parent.mkdir(parents=True)
    link.write_bytes(b"MZ")
    orig = Path.is_file

    def fake_is_file(self):
        s = str(self).replace("/", "\\")
        if "WinGet" in s and "Links" in s:
            raise _oserror_448(self)
        return orig(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    reasons = []
    found = bw.resolve_opencode_cmd(
        env={"LOCALAPPDATA": str(la)},
        which=lambda n: None,
        reasons=reasons,
    )
    assert found is None
    assert reasons


def test_fr7302_fuel_ps1_swallows_448():
    src = (
        Path(__file__).resolve().parents[1]
        / "tray"
        / "tools"
        / "Get-BobOpencodeFuel.ps1"
    ).read_text(encoding="utf-8")
    assert "FR #7302" in src
    assert "untrusted mount" in src


def test_fr7302_link_ok_still_returns_winget_path(tmp_path):
    la = tmp_path / "la"
    link = la / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    link.parent.mkdir(parents=True)
    link.write_bytes(b"MZ")
    found = bw.resolve_opencode_cmd(env={"LOCALAPPDATA": str(la)}, which=lambda n: None)
    assert found == str(link)
