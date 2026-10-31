"""FR #5585: already-installed hosts are present/skipped, not would_write/chrome:true."""
from __future__ import annotations

import airc_extension as ex
from repo_layout import ROOT

EXT = ex.DEFAULT_EXTENSION_ID
PRESENT = (["1"], [f"{EXT};https://clients2.google.com/service/update2/crx"])
ABSENT = ([], [])


def _reader_already(_host: str, _product: str):
    return PRESENT


def _reader_absent(_host: str, _product: str):
    return ABSENT


def test_fr5585_whatif_already_present_not_would_write():
    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["MARCHHARE"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        read_forcelist=_reader_already,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(AssertionError("no write")),
    )
    row = body["hosts"][0]
    assert row["host"] == "MARCHHARE"
    assert row["would_write"] is False
    assert row.get("skipped") == "already"
    assert row.get("state") == "present"
    assert body["wrote_registry"] is False


def test_fr5585_status_already_present_skipped_already():
    body = ex.fill_holes_work(
        "status",
        ldap_enum=lambda: ["dodo"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        read_forcelist=_reader_already,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(AssertionError("no write")),
    )
    row = body["hosts"][0]
    assert row["would_write"] is False
    assert row.get("skipped") == "already"


def test_fr5585_whatif_absent_still_would_write():
    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["pc1"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        read_forcelist=_reader_absent,
    )
    assert body["hosts"][0]["would_write"] is True
    assert body["hosts"][0].get("skipped") != "already"


def test_fr5585_install_already_present_not_chrome_true():
    writes: list[tuple] = []

    def apply(host, product, value):
        writes.append((host, product, value))
        return False

    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["MARCHHARE"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        apply_force_install=apply,
        read_forcelist=_reader_already,
    )
    row = body["hosts"][0]
    assert row.get("chrome") is False
    assert row.get("edge") is False
    assert row.get("skipped") == "already"
    assert body["wrote_registry"] is False
    assert writes  # apply still probed/called; no-op return


def test_fr5585_default_apply_returns_false_when_present(monkeypatch):
    class FakeKey:
        pass

    def enum_value(_key, i):
        if i == 0:
            return ("1", f"{EXT};https://x", 1)
        raise OSError("no more")

    set_names: list[str] = []

    def set_value(_key, name, *_a):
        set_names.append(name)

    import winreg

    monkeypatch.setattr(winreg, "ConnectRegistry", lambda *_a: object())
    monkeypatch.setattr(winreg, "CreateKey", lambda *_a: FakeKey())
    monkeypatch.setattr(winreg, "EnumValue", enum_value)
    monkeypatch.setattr(winreg, "SetValueEx", set_value)
    monkeypatch.setattr(winreg, "CloseKey", lambda *_a: None)
    wrote = ex.default_apply_force_install("pc1", "chrome", ex.force_install_value())
    assert wrote is False
    assert set_names == []


def test_fr5585_pins():
    src = (ROOT / "airc" / "scripts" / "airc_extension.py").read_text(encoding="utf-8")
    assert "FR #5585" in src
    assert "probe_host_forcelist" in src
    assert "skipped" in src and "already" in src
    assert not (ROOT / "airc" / "scripts" / "airc_extension.py").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )

def test_fr5585_credman_apply_as_propagates_false(monkeypatch):
    """CredMan path must not treat void/None as wrote=True (FR #5585)."""
    monkeypatch.setattr(ex, "default_apply_force_install", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "shutil.which", lambda name: "C:\\Windows\\System32\\net.exe" if name == "net" else None
    )

    class P:
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: P())
    assert (
        ex.default_apply_force_install_as(
            "h", "chrome", ex.force_install_value(), "u", "FAKE_pw"
        )
        is False
    )

    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc1"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(
            PermissionError("Access is denied")
        ),
        apply_force_install_as=lambda *_a: False,
        credman_reader=lambda: {"username": "u", "password": "FAKE_pw"},
        read_forcelist=_reader_already,
    )
    row = body["hosts"][0]
    assert row.get("chrome") is False
    assert row.get("edge") is False
    assert row.get("skipped") == "already"
    assert body["wrote_registry"] is False
