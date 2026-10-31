"""FR #5364: fill-holes retries with CredMan PriorityAirc/ExtensionAdmin on access-denied."""
from __future__ import annotations

import airc_extension as ex


def test_fr5364_credman_target_name():
    assert ex.CREDMAN_TARGET == "PriorityAirc/ExtensionAdmin"


def test_fr5364_access_denied_retries_with_credman():
    applied: list[tuple] = []

    def apply_reg(host: str, product: str, value: str) -> None:
        raise PermissionError("Access is denied")

    def apply_as(host: str, product: str, value: str, username: str, password: str) -> None:
        applied.append((host, product, username, password))

    def creds():
        return {"username": "EXAMPLE_admin", "password": "FAKE_secret"}

    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc-deny"],
        ping_host=lambda _h: True,
        apply_force_install=apply_reg,
        apply_force_install_as=apply_as,
        credman_reader=creds,
    )
    assert body["wrote_registry"] is True
    hosts = {h["host"]: h for h in body["hosts"]}
    assert hosts["pc-deny"]["ok"] is True
    assert hosts["pc-deny"].get("auth") == "credman"
    assert [a[0] for a in applied] == ["pc-deny", "pc-deny"]
    assert all(a[2] == "EXAMPLE_admin" for a in applied)
    blob = str(body)
    assert "FAKE_secret" not in blob
    assert "password=" not in blob.lower()


def test_fr5364_missing_credman_fail_closed():
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc-deny"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(OSError(5, "Access is denied")),
        credman_reader=lambda: {},
    )
    hosts = {h["host"]: h for h in body["hosts"]}
    assert hosts["pc-deny"]["ok"] is False
    assert hosts["pc-deny"]["error"] == "credman-missing"
    assert body["wrote_registry"] is False


def test_fr5364_non_access_denied_does_not_touch_credman():
    reads = []

    def apply_reg(host: str, product: str, value: str) -> None:
        raise TimeoutError("rpc timeout")

    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc-to"],
        ping_host=lambda _h: True,
        apply_force_install=apply_reg,
        credman_reader=lambda: reads.append("read") or {"username": "u", "password": "FAKE_x"},
    )
    assert reads == []
    assert body["hosts"][0]["error"] == "TimeoutError"


def test_fr5364_whatif_skips_credman():
    reads = []
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc1"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *_a: None,
        credman_reader=lambda: reads.append(1) or {},
        whatif=True,
    )
    assert reads == []
    assert body["hosts"][0]["would_write"] is True


def test_fr5364_pins_utf8():
    from pathlib import Path
    from repo_layout import ROOT

    src = (ROOT / "airc" / "scripts" / "airc_extension.py").read_text(encoding="utf-8")
    assert "FR #5364" in src
    assert "PriorityAirc/ExtensionAdmin" in src
    assert "credman-missing" in src
    assert not (ROOT / "airc" / "scripts" / "airc_extension.py").read_bytes().startswith(b"\xef\xbb\xbf")
