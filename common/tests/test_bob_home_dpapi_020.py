"""0.1.19 on MarchHare: the home migration (run by the SYSTEM ircBob service) copied Administrator's legacy
``~\\.agentic-irc-bobiverse\\identity.json`` - DPAPI-protected for Administrator - into the service home. SYSTEM cannot decrypt it,
so ``seal.load_ident`` raised ``CryptUnprotectData failed`` and ircBob crashed every ~2 s. The migration must skip user-bound
DPAPI files the current account cannot decrypt (and still copy everything else)."""
import json
import sys
from pathlib import Path

import pytest

import bob_home
import protect

WIN = sys.platform == "win32"


def _legacy(tmp_path):
    old = tmp_path / "profile" / ".agentic-irc-bobiverse"
    old.mkdir(parents=True)
    (old / "digest.json").write_text("{}", encoding="utf-8")
    (old / "nickserv.password").write_text("plain-secret-not-printed", encoding="utf-8")
    return old


def _fake_foreign_blob(path: Path):
    path.write_bytes(protect.MAGIC + b"\x01\x00\x00\x00foreign-account-ciphertext")


def test_foreign_user_bound_identity_is_skipped(tmp_path, monkeypatch):
    old = _legacy(tmp_path)
    _fake_foreign_blob(old / "identity.json")
    calls = []

    def fake_unprotect(data):  # what SYSTEM sees for Administrator's blob
        calls.append(data)
        raise OSError("CryptUnprotectData failed")

    monkeypatch.setattr(protect, "_dpapi_unprotect", fake_unprotect)
    new = tmp_path / "svc" / "home"
    res = bob_home.migrate_legacy(new, old_homes=[old])
    assert res["status"] == "migrated" and calls
    assert not (new / "identity.json").exists()                       # NOT carried across accounts
    assert res["skipped_protected"] == ["identity.json"]
    assert (new / "digest.json").is_file() and (new / "nickserv.password").is_file()   # everything else still migrated
    assert (new / bob_home.MARKER).is_file()
    assert json.loads((new / bob_home.MARKER).read_text())["skipped_protected"] == ["identity.json"]
    assert (old / "identity.json").is_file()                          # the old home stays untouched as a backup


def test_readable_protected_identity_and_plain_files_are_still_copied(tmp_path, monkeypatch):
    old = _legacy(tmp_path)
    _fake_foreign_blob(old / "identity.json")
    (old / "machine.bin").write_bytes(protect.MAGIC_MACHINE + b"machine-bound")
    (old / "plain.json").write_text('{"pk": "x"}', encoding="utf-8")
    monkeypatch.setattr(protect, "_dpapi_unprotect", lambda data: b"{}")   # same account: decrypt works
    new = tmp_path / "svc" / "home"
    res = bob_home.migrate_legacy(new, old_homes=[old])
    assert res["skipped_protected"] == []
    for n in ("identity.json", "machine.bin", "plain.json", "digest.json"):
        assert (new / n).is_file(), n


def test_machine_bound_and_plain_never_probe_dpapi(tmp_path, monkeypatch):
    old = _legacy(tmp_path)
    (old / "machine.bin").write_bytes(protect.MAGIC_MACHINE + b"machine-bound")
    monkeypatch.setattr(protect, "_dpapi_unprotect", lambda data: (_ for _ in ()).throw(AssertionError("must not be called")))
    new = tmp_path / "svc" / "home"
    res = bob_home.migrate_legacy(new, old_homes=[old])
    assert res["status"] == "migrated" and (new / "machine.bin").is_file()


@pytest.mark.skipif(not WIN, reason="real DPAPI round trip")
def test_real_dpapi_blob_of_this_account_is_copied(tmp_path):
    old = _legacy(tmp_path)
    protect.write_secret_bytes(old / "identity.json", b'{"pk": "abc"}')
    new = tmp_path / "svc" / "home"
    res = bob_home.migrate_legacy(new, old_homes=[old])
    assert res["skipped_protected"] == [] and (new / "identity.json").is_file()
    assert protect.read_secret_bytes(new / "identity.json") == b'{"pk": "abc"}'


@pytest.mark.skipif(not WIN, reason="real DPAPI")
def test_corrupt_user_blob_counts_as_unreadable(tmp_path):
    old = _legacy(tmp_path)
    (old / "identity.json").write_bytes(protect.MAGIC + b"not a real dpapi blob")
    new = tmp_path / "svc" / "home"
    res = bob_home.migrate_legacy(new, old_homes=[old])
    assert res["skipped_protected"] == ["identity.json"] and not (new / "identity.json").exists()