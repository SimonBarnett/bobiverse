"""FR #6274: SeBackupPrivilege + FILE_FLAG_BACKUP_SEMANTICS auth.json read.

Grok agent.exe resets auth.json to Administrator-only (inheritance off).
LocalSystem must still fetch a live weekly reading without changing ACLs.
Fixtures use FAKE_ only; never 82/74/43/75/35.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402

FILE_FLAG_BACKUP_SEMANTICS = 0x02000000


def _flamingo_shaped_auth(key: str = "FAKE_BACKUP_SESSION_KEY_ONLY") -> dict:
    return {
        "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828": {
            "auth_mode": "oidc",
            "email": "backup-fake@example.test",
            "expires_at": "2099-01-01T00:00:00Z",
            "first_name": "Fake",
            "key": key,
            "refresh_token": "FAKE_REFRESH_FOR_TESTS_ONLY",
            "user_id": "fake-user-backup",
        }
    }


def test_fr6274_backup_reader_requests_backup_semantics_flag(tmp_path: Path, monkeypatch):
    """CreateFile must be called with FILE_FLAG_BACKUP_SEMANTICS (FR #6274)."""
    if os.name != "nt":
        pytest.skip("Windows-only")
    path = tmp_path / "auth.json"
    payload = json.dumps(_flamingo_shaped_auth()).encode("utf-8")
    path.write_bytes(payload)

    flags_seen: list[int] = []

    import ctypes
    from ctypes import wintypes

    real_windll = ctypes.WinDLL

    def windll_factory(name, *a, **k):
        dll = real_windll(name, *a, **k)
        if str(name).lower() in ("kernel32", "kernel32.dll"):
            orig_create = dll.CreateFileW

            def spy_create(path_name, access, share, sec, disp, flags, template):
                flags_seen.append(int(flags))
                return orig_create(path_name, access, share, sec, disp, flags, template)

            # Preserve HANDLE prototypes the helper will overwrite on this private dll.
            spy_create.restype = wintypes.HANDLE  # type: ignore[attr-defined]
            spy_create.argtypes = [  # type: ignore[attr-defined]
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ]
            dll.CreateFileW = spy_create  # type: ignore[method-assign]
        return dll

    monkeypatch.setattr(ctypes, "WinDLL", windll_factory)
    data, err = bobreport.read_bytes_win32_backup(path)
    assert err is None, f"backup read failed win32={err}"
    assert data == payload
    assert flags_seen, "CreateFileW was not called"
    assert any(f & FILE_FLAG_BACKUP_SEMANTICS for f in flags_seen)


@pytest.mark.skipif(os.name != "nt", reason="backup path is Windows-only (os.name==nt)")
def test_fr6274_load_prefers_backup_over_normal_read(tmp_path: Path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(_flamingo_shaped_auth("FAKE_VIA_BACKUP")), encoding="utf-8")

    def boom_read_text(*a, **k):
        raise PermissionError(13, "Access is denied", str(path))

    monkeypatch.setattr(Path, "read_text", boom_read_text)
    monkeypatch.setattr(
        bobreport,
        "read_text_win32_backup",
        lambda p: (json.dumps(_flamingo_shaped_auth("FAKE_VIA_BACKUP")), None),
    )
    token, err, label = bobreport.load_grok_auth_session(path)
    assert err is None
    assert token == "FAKE_VIA_BACKUP"
    assert label == "backup-fake@example.test"


@pytest.mark.skipif(os.name != "nt", reason="backup path is Windows-only (os.name==nt)")
def test_fr6274_unreadable_includes_win32_when_both_fail(tmp_path: Path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bobreport, "read_text_win32_backup", lambda p: (None, 5))

    def boom_read_text(*a, **k):
        raise PermissionError(13, "Access is denied", str(path))

    monkeypatch.setattr(Path, "read_text", boom_read_text)
    token, err, _label = bobreport.load_grok_auth_session(path)
    assert token is None
    assert err == "auth-file-unreadable:win32-5"


def test_fr6274_backup_fetch_survives_admin_only_acl(tmp_path: Path, monkeypatch):
    """Strip inherited ACLs to Admin-only; backup path must still load without ACL edits."""
    if os.name != "nt":
        pytest.skip("Windows-only")
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(_flamingo_shaped_auth("FAKE_ACL_STRIP_KEY")), encoding="utf-8")
    # Capture SDDL before strip for permission-unchanged-by-ear assertion after read.
    before = subprocess.run(
        ["icacls", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Inheritance off + Administrators only (agent.exe shape).
    r1 = subprocess.run(
        ["icacls", str(path), "/inheritance:r"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    r2 = subprocess.run(
        ["icacls", str(path), "/grant:r", "Administrators:F"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r1.returncode != 0 or r2.returncode != 0:
        pytest.skip(f"icacls unavailable: {r1.stderr or r2.stderr}")

    after_strip = subprocess.run(
        ["icacls", str(path)], capture_output=True, text=True, timeout=30
    ).stdout

    # Normal open may fail depending on who runs pytest; backup must be attempted.
    data, win_err = bobreport.read_bytes_win32_backup(path)
    if data is None:
        # Seat without SeBackupPrivilege cannot prove live ACL bypass — still
        # assert the helper was the contract and did not rewrite ACLs.
        after_read = subprocess.run(
            ["icacls", str(path)], capture_output=True, text=True, timeout=30
        ).stdout
        assert after_read == after_strip, "ear must not change auth.json ACLs"
        pytest.skip(f"SeBackupPrivilege not effective here (win32={win_err})")

    token, err, label = bobreport.load_grok_auth_session(path)
    assert err is None
    assert token == "FAKE_ACL_STRIP_KEY"
    assert label == "backup-fake@example.test"

    after_read = subprocess.run(
        ["icacls", str(path)], capture_output=True, text=True, timeout=30
    ).stdout
    assert after_read == after_strip, "ear must not change auth.json ACLs on backup read"
    assert before.returncode == 0  # silence unused if needed


@pytest.mark.skipif(os.name != "nt", reason="backup path is Windows-only (os.name==nt)")
def test_fr6274_fetch_live_uses_backup_when_read_text_denied(tmp_path: Path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(_flamingo_shaped_auth("FAKE_LIVE_BACKUP_KEY")), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setattr(
        bobreport,
        "read_text_win32_backup",
        lambda p: (json.dumps(_flamingo_shaped_auth("FAKE_LIVE_BACKUP_KEY")), None),
    )

    def boom_read_text(*a, **k):
        raise PermissionError(13, "Access is denied", str(path))

    monkeypatch.setattr(Path, "read_text", boom_read_text)

    class _Resp:
        def read(self):
            return json.dumps(
                {
                    "config": {
                        "creditUsagePercent": 61,
                        "currentPeriod": {
                            "type": "USAGE_PERIOD_TYPE_WEEKLY",
                            "end": "2026-11-20T12:00:00Z",
                        },
                    }
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _Resp(),
    )
    reading = bobreport.fetch_live_xai_weekly(
        now=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    )
    assert reading is not None
    assert reading.get("fresh") is True
    assert reading.get("remaining_pct") == 39
    assert reading.get("used_pct") == 61
    assert bobreport._last_xai_acquisition.get("error") in (None, "")

def test_mrb6292_backup_reader_uses_private_windll():
    """MRB #6292: read_bytes_win32_backup must use ctypes.WinDLL(..., use_last_error=True)."""
    import inspect
    src = inspect.getsource(bobreport.read_bytes_win32_backup)
    assert 'WinDLL("kernel32", use_last_error=True)' in src
    assert 'WinDLL("advapi32", use_last_error=True)' in src
    assert "ctypes.windll.kernel32" not in src
    assert "ctypes.get_last_error" in src
