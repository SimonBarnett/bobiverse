"""FR #5292: EXTENSION LDAP enum + per-host registry ForceInstall fallback."""
from __future__ import annotations

import threading
import time

import airc_console as ac
import airc_extension as ex
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5292_reachable_ad_hosts_get_chrome_and_edge_keys():
    applied: list[tuple[str, str]] = []

    def ldap():
        return ["pc-ok", "pc-dead"]

    def ping(host: str) -> bool:
        return host == "pc-ok"

    def apply_reg(host: str, product: str, value: str) -> None:
        # FR #5661: ICMP fail no longer skips apply; dead host must raise.
        if host == "pc-dead":
            raise OSError(53, "The network path was not found")
        applied.append((host, product, value))

    body = ex.fill_holes_work(
        "install",
        ldap_enum=ldap,
        ping_host=ping,
        apply_force_install=apply_reg,
        tcp_probe=lambda h, _p=445: h == "pc-ok",
        whatif=False,
    )
    assert body["wrote_gpo"] is False
    assert body["wrote_registry"] is True
    hosts = {h["host"]: h for h in body["hosts"]}
    assert hosts["pc-ok"]["ok"] is True
    assert hosts["pc-dead"]["ok"] is False
    assert hosts["pc-dead"]["error"] in {"smb_blocked", "host_down"}
    assert hosts["pc-dead"]["error"] != "unreachable"
    products = {(h, p) for h, p, _ in applied}
    assert ("pc-ok", "chrome") in products
    assert ("pc-ok", "edge") in products
    assert all(h == "pc-ok" for h, _p, _v in applied)
    assert all(ex.DEFAULT_EXTENSION_ID in v for _h, _p, v in applied)
    assert "clients2.google.com" in applied[0][2]


def test_fr5292_does_not_invent_hosts_outside_ldap():
    seen: list[str] = []

    def ldap():
        return ["ad-only"]

    def ping(host: str) -> bool:
        seen.append(host)
        return True

    def apply_reg(host: str, product: str, value: str) -> None:
        seen.append(f"write:{host}")

    body = ex.fill_holes_work(
        "install",
        ldap_enum=ldap,
        ping_host=ping,
        apply_force_install=apply_reg,
        extra_hosts=["invented-box"],
    )
    assert "invented-box" not in seen
    assert all(h["host"] == "ad-only" for h in body["hosts"])


def test_fr5292_whatif_does_not_write():
    writes = []
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["pc1"],
        ping_host=lambda _h: True,
        read_forcelist=lambda _h, _p: ([], []),
        apply_force_install=lambda *a: writes.append(a),
        whatif=True,
    )
    assert writes == []
    assert body["wrote_registry"] is False
    assert body["hosts"][0]["ok"] is True
    assert body["hosts"][0]["would_write"] is True


def test_fr5292_isolated_and_no_password_on_wire():
    def ldap():
        time.sleep(0.2)
        return ["pc1"]

    core = _core(
        extension_runner=lambda **kw: ex.run_extension_verb(
            worker=lambda **w: ex.fill_holes_work(
                w.get("action", "install"),
                ldap_enum=ldap,
                ping_host=lambda _h: True,
                apply_force_install=lambda *_a: None,
                whatif=w.get("whatif", False),
            ),
            **kw,
        )
    )
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=cafecafe EXTENSION install")
    elapsed = time.perf_counter() - t0
    assert hr and hr.action == "extension"
    assert "EXTENSION accepted" in (hr.reply or "")
    assert elapsed < 0.15
    assert "password=" not in (hr.reply or "").lower()
    assert threading.main_thread().is_alive()
