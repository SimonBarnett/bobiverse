"""FR #5526: native CredReadW helper + PRIORITY/LEGION error mapping (no PS timeout)."""
from __future__ import annotations

import os
import time
import uuid

import pytest

import airc_credman as cm
import airc_legion as lg
import airc_priority as ap
from repo_layout import ROOT


def test_fr5526_credman_module_imports_clean():
    assert hasattr(cm, "read_generic_credential")
    assert hasattr(cm, "CredmanError")
    assert hasattr(cm, "CredmanPair")
    assert not (ROOT / "airc" / "scripts" / "airc_credman.py").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )


def test_fr5526_priority_missing_maps_credman_missing(monkeypatch):
    monkeypatch.setattr(cm, "read_generic_credential", lambda _t: None)
    with pytest.raises(ap.PriorityConfigError, match="credman-missing"):
        ap.fetch_credman_password("PriorityWeb/missing-target")


def test_fr5526_priority_winerror_maps_read_failed(monkeypatch):
    def boom(_t):
        raise cm.CredmanError("winerror-1312")

    monkeypatch.setattr(cm, "read_generic_credential", boom)
    with pytest.raises(ap.PriorityConfigError, match="credman-read-failed:winerror-1312"):
        ap.fetch_credman_password("PriorityWeb/x")


def test_fr5526_priority_empty_password(monkeypatch):
    monkeypatch.setattr(
        cm, "read_generic_credential", lambda _t: cm.CredmanPair("u", "")
    )
    with pytest.raises(ap.PriorityConfigError, match="credman-empty"):
        ap.fetch_credman_password("PriorityWeb/x")


def test_fr5526_legion_missing_and_empty(monkeypatch):
    monkeypatch.setattr(cm, "read_generic_credential", lambda _t: None)
    with pytest.raises(lg.LegionCredmanError, match="credman-missing"):
        lg.read_legion_credman()

    monkeypatch.setattr(
        cm, "read_generic_credential", lambda _t: cm.CredmanPair("u", "")
    )
    with pytest.raises(lg.LegionCredmanError, match="credman-empty") as ei:
        lg.read_legion_credman()
    assert "FAKE" not in str(ei.value)
    assert "password" not in str(ei.value).lower() or "credman-empty" in str(ei.value)


def test_fr5526_exception_never_carries_secret(monkeypatch):
    secret = "FAKE_SECRET_BLOB_NEVER_IN_EXC"

    def boom(_t):
        raise cm.CredmanError("winerror-5")

    monkeypatch.setattr(cm, "read_generic_credential", boom)
    with pytest.raises(ap.PriorityConfigError) as ei:
        ap.fetch_credman_password("PriorityWeb/x")
    assert secret not in str(ei.value)
    assert secret not in repr(ei.value)


def test_fr5526_legacy_runner_still_uses_timeout_30():
    seen: dict = {}

    def fake_runner(argv, *, capture_output=True, text=True, timeout=None):
        seen["timeout"] = timeout
        seen["argv0"] = argv[0].lower() if argv else ""
        class P:
            returncode = 2
            stdout = "CRED_MISSING"
            stderr = ""

        return P()

    with pytest.raises(ap.PriorityConfigError, match="credman-missing"):
        ap.fetch_credman_password("PriorityWeb/x", runner=fake_runner)
    assert seen["timeout"] == 30
    assert "powershell" in seen["argv0"]


def test_fr5526_default_path_source_avoids_powershell_subprocess():
    prio = (ROOT / "airc" / "scripts" / "airc_priority.py").read_text(encoding="utf-8")
    leg = (ROOT / "airc" / "scripts" / "airc_legion.py").read_text(encoding="utf-8")
    # Default branch must call airc_credman before any runner= PowerShell path.
    assert "import airc_credman" in prio
    assert "import airc_credman" in leg
    fetch_idx = prio.index("def fetch_credman_password")
    native_idx = prio.index("import airc_credman", fetch_idx)
    legacy_idx = prio.index("Legacy PowerShell", fetch_idx)
    assert native_idx < legacy_idx
    assert "airc_credman" in Build_text()


def Build_text() -> str:
    return (ROOT / "airc" / "scripts" / "Build-Airc.ps1").read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="CredReadW is Windows-only")
def test_fr5526_windows_missing_target_is_fast():
    target = f"PriorityWeb/fr5526-missing-{uuid.uuid4().hex}"
    t0 = time.perf_counter()
    got = cm.read_generic_credential(target)
    elapsed = time.perf_counter() - t0
    assert got is None
    assert elapsed < 1.0


def test_fr5526_packaging_pins():
    build = Build_text()
    assert "airc_credman" in build
    common = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(
        encoding="utf-8-sig"
    )
    start = common.index("function Get-BobiverseAircClientAllowedScriptNames")
    end = common.index("function Get-BobiverseAircMsiAgentLayerScriptNames")
    assert "airc_credman.py" in common[start:end]
    pack = (ROOT / "airc" / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(
        encoding="utf-8"
    )
    assert "airc_credman.py" in pack
    allow = (ROOT / "airc" / "tests" / "test_fr3514_client_allowlist_payload.py").read_text(
        encoding="utf-8"
    )
    assert r"scripts\airc_credman.py" in allow
    assert "len(CLIENT_REMAINING_FILES) == 33" in allow
