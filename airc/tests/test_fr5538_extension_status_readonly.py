"""FR #5538: EXTENSION status is read-only; forcelist appends; no DC writes."""
from __future__ import annotations

import airc_extension as ex


def test_fr5538_status_does_not_write():
    writes: list[tuple] = []
    body = ex.fill_holes_work(
        "status",
        ldap_enum=lambda: ["pc1", "dc1"],
        ping_host=lambda _h: True,
        read_forcelist=lambda _h, _p: ([], []),
        apply_force_install=lambda *a: writes.append(a),
        is_dc=lambda h: h == "dc1",
        whatif=False,
    )
    assert writes == []
    assert body["wrote_registry"] is False
    hosts = {h["host"]: h for h in body["hosts"]}
    assert hosts["pc1"].get("would_write") is True
    assert hosts["pc1"].get("skipped") == "status"
    assert hosts["dc1"].get("skipped") == "dc"


def test_fr5538_install_skips_dc_but_writes_members():
    writes: list[tuple] = []
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc1", "dc1"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *a: writes.append(a),
        is_dc=lambda h: h.lower() == "dc1",
    )
    hosts = {h["host"]: h for h in body["hosts"]}
    assert hosts["dc1"].get("skipped") == "dc"
    assert ("dc1", "chrome") not in {(h, p) for h, p, *_ in writes}
    assert any(h == "pc1" and p == "chrome" for h, p, *_ in writes)
    assert body["wrote_registry"] is True


def test_fr5538_next_forcelist_name_appends_and_skips_present():
    assert ex.next_forcelist_name(["1"], ["other;https://x"], "abc") == "2"
    assert ex.next_forcelist_name(["1", "2"], ["x", "abc;https://x"], "abc") is None
    assert ex.next_forcelist_name([], [], "abc") == "1"


def test_fr5538_default_apply_uses_next_name(monkeypatch):
    set_names: list[str] = []

    class FakeKey:
        pass

    def enum_value(_key, i):
        if i == 0:
            return ("1", "already;https://x", 1)
        raise OSError("no more")

    def set_value(key, name, _res, _typ, value):
        set_names.append(name)

    import winreg

    monkeypatch.setattr(winreg, "ConnectRegistry", lambda *_a: object())
    monkeypatch.setattr(winreg, "CreateKey", lambda *_a: FakeKey())
    monkeypatch.setattr(winreg, "EnumValue", enum_value)
    monkeypatch.setattr(winreg, "SetValueEx", set_value)
    monkeypatch.setattr(winreg, "CloseKey", lambda *_a: None)
    ex.default_apply_force_install("pc1", "chrome", ex.force_install_value())
    assert set_names == ["2"]


def test_fr5538_default_dc_enum_skips_without_is_dc_inject():
    writes: list[tuple] = []
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc1", "WALRUS"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *a: writes.append(a),
        dc_enum=lambda: ["WALRUS"],
    )
    hosts = {h["host"]: h for h in body["hosts"]}
    assert hosts["WALRUS"].get("skipped") == "dc"
    assert not any(h == "WALRUS" for h, *_ in writes)
    assert any(h == "pc1" for h, *_ in writes)


def test_fr5538_default_dc_hostnames_uses_adsi_not_stub():
    src = open(ex.__file__, encoding="utf-8").read()
    start = src.index("def default_dc_hostnames")
    end = src.index("\ndef force_install_value", start)
    body = src[start:end]
    assert "adsisearcher" in body
    assert "8192" in body
    assert "PropertiesToLoad" in body
    assert "subprocess.run" in body
