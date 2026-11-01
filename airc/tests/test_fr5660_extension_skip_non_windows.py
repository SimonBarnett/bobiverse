"""FR #5660: Samba / non-Windows hosts must not be reported as extension present."""
from __future__ import annotations

import airc_extension as ex

EXT = ex.DEFAULT_EXTENSION_ID
# Samba winreg can persist a forcelist written by a prior CreateKey — still not Windows.
SAMBA_PRESENT = (["1"], [f"{EXT};https://clients2.google.com/service/update2/crx"])


def test_fr5660_forcelist_requires_id_before_semicolon():
    assert ex.forcelist_value_has_extension(
        f"{EXT};https://clients2.google.com/service/update2/crx", EXT
    )
    assert not ex.forcelist_value_has_extension(f"other{EXT};https://x", EXT)
    assert not ex.forcelist_value_has_extension(f"prefix-{EXT}-suffix;https://x", EXT)
    assert not ex.forcelist_value_has_extension("", EXT)
    assert ex.next_forcelist_name(["1"], [f"other;https://x"], EXT) == "2"
    assert ex.next_forcelist_name(["1"], [f"{EXT};https://x"], EXT) is None


def test_fr5660_registry_values_look_like_windows():
    assert not ex.registry_values_look_like_windows(
        {"SystemRoot": r"c:\Windows", "CurrentVersion": "6.1"}
    )
    assert ex.registry_values_look_like_windows(
        {
            "SystemRoot": r"C:\Windows",
            "CurrentVersion": "6.3",
            "ProductName": "Windows Server 2019 Standard",
            "CurrentBuild": "17763",
        }
    )
    assert ex.registry_values_look_like_windows(
        {"CurrentBuildNumber": "26100", "ProductName": "Windows 10 Pro"}
    )
    assert not ex.registry_values_look_like_windows({})


def test_fr5660_whatif_samba_skipped_not_windows_not_present():
    writes: list = []

    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["dodo"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        is_windows_host=lambda _h: False,
        read_forcelist=lambda _h, _p: SAMBA_PRESENT,
        apply_force_install=lambda *a: writes.append(a) or True,
    )
    row = body["hosts"][0]
    assert row["host"] == "dodo"
    assert row.get("skipped") == "not_windows"
    assert row.get("would_write") is False
    assert row.get("state") != "present"
    assert row.get("chrome") is not True
    assert row.get("edge") is not True
    assert writes == []
    assert body["wrote_registry"] is False


def test_fr5660_status_samba_skipped_not_windows():
    body = ex.fill_holes_work(
        "status",
        ldap_enum=lambda: ["dodo"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        is_windows_host=lambda _h: False,
        read_forcelist=lambda _h, _p: SAMBA_PRESENT,
    )
    row = body["hosts"][0]
    assert row.get("skipped") == "not_windows"
    assert row.get("state") != "present"
    assert row.get("would_write") is False


def test_fr5660_install_does_not_write_non_windows():
    writes: list = []

    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["dodo"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        is_windows_host=lambda _h: False,
        read_forcelist=lambda _h, _p: ([], []),
        apply_force_install=lambda *a: writes.append(a) or True,
    )
    assert body["hosts"][0].get("skipped") == "not_windows"
    assert writes == []
    assert body["wrote_registry"] is False


def test_fr5660_windows_host_still_reports_present():
    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["WALRUS"],
        ping_host=lambda _h: True,
        is_dc=lambda _h: False,
        is_windows_host=lambda _h: True,
        read_forcelist=lambda _h, _p: SAMBA_PRESENT,
    )
    row = body["hosts"][0]
    assert row.get("skipped") == "already"
    assert row.get("state") == "present"
    assert row["chrome"] is True
    assert row["edge"] is True


def test_fr5660_pins_helpers_and_docs():
    from pathlib import Path

    src = Path(ex.__file__).read_text(encoding="utf-8")
    assert "FR #5660" in src
    assert "not_windows" in src
    assert "registry_values_look_like_windows" in src
    assert "forcelist_value_has_extension" in src
    docs = Path(__file__).resolve().parents[1] / "docs" / "airc-remote-control.md"
    assert "FR #5660" in docs.read_text(encoding="utf-8")
    assert "not_windows" in docs.read_text(encoding="utf-8")
