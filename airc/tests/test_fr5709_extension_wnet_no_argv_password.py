"""FR #5709 / #5708: EXTENSION CredMan IPC$ via WNetAddConnection2W (no net use argv).

Password must never appear on a subprocess command line (4688 / process argv).
IPC failures must keep the real Win32 code (53 path-not-found is not auth_failed).
"""
from __future__ import annotations

from pathlib import Path

import airc_extension as ex

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "airc" / "scripts" / "airc_extension.py"


def test_fr5709_source_uses_wnet_not_net_use_password():
    src = SRC.read_text(encoding="utf-8")
    wnet_src = (ROOT / "airc" / "scripts" / "airc_wnet.py").read_text(encoding="utf-8")
    assert "FR #5709" in src
    # FR #5726: ctypes WNet lives in shared airc_wnet; EXTENSION imports it.
    assert "from airc_wnet import" in src
    assert "wnet_add_ipc" in src
    assert "WNetAddConnection2W" in wnet_src
    fn = src[src.index("def default_apply_force_install_as") :]
    fn = fn[: fn.index("\ndef default_apply_force_install")]
    assert "wnet_add_ipc" in fn
    assert "wnet_cancel" in fn
    # Must not build net use argv with the password positional.
    assert "net" not in fn or '"use"' not in fn
    assert "[net, \"use\"" not in fn
    assert "password," not in fn.replace("password: str", "")
    assert not SRC.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5709_apply_as_never_calls_subprocess_with_password(monkeypatch):
    calls: list[list[str]] = []

    def boom_run(args, **_k):
        calls.append([str(a) for a in args])
        raise AssertionError("subprocess.run must not be used for IPC$ auth")

    monkeypatch.setattr(ex, "default_apply_force_install", lambda *_a, **_k: True)
    monkeypatch.setattr(ex, "wnet_add_ipc", lambda host, user, pw: r"\\%s\IPC$" % host)
    cancelled: list[str] = []
    monkeypatch.setattr(ex, "wnet_cancel", lambda remote: cancelled.append(remote))
    monkeypatch.setattr("subprocess.run", boom_run)

    assert (
        ex.default_apply_force_install_as(
            "redqueen", "chrome", ex.force_install_value(), "EXAMPLE\\admin", "FAKE_secret"
        )
        is True
    )
    assert calls == []
    assert cancelled == [r"\\redqueen\IPC$"]


def test_fr5709_wnet_failure_preserves_winerror(monkeypatch):
    def fail(_host, _user, _pw):
        err = OSError(53, "The network path was not found")
        err.winerror = 53
        raise err

    monkeypatch.setattr(ex, "wnet_add_ipc", fail)
    monkeypatch.setattr(ex, "wnet_cancel", lambda *_a, **_k: None)
    try:
        ex.default_apply_force_install_as(
            "redqueen", "chrome", ex.force_install_value(), "u", "FAKE_pw"
        )
        raise AssertionError("expected OSError")
    except OSError as exc:
        assert int(getattr(exc, "winerror", 0) or exc.errno or 0) == 53
        assert "FAKE_pw" not in str(exc)


def test_fr5708_path_not_found_not_auth_failed():
    """CredMan identity + WinError 53 must classify, not blanket auth_failed."""

    def boom_as(host, product, value, username, password):
        err = OSError(53, "The network path was not found")
        err.winerror = 53
        raise err

    body = ex.fill_holes_work(
        "install",
        whatif=False,
        ldap_enum=lambda: ["REDQUEEN"],
        ping_host=lambda _h: True,
        tcp_probe=lambda _h, _p=445: False,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(
            AssertionError("SYSTEM path unused when credman resolved")
        ),
        apply_force_install_as=boom_as,
        credman_reader=lambda: {
            "username": "EXAMPLE\\admin",
            "password": "FAKE_secret",
        },
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] != "auth_failed"
    assert row["error"] in {"smb_blocked", "host_down", "unreachable"}
    assert row.get("detail")
    assert "FAKE_secret" not in str(body)


def test_fr5708_logon_failure_is_auth_failed_with_detail():
    def boom_as(host, product, value, username, password):
        err = OSError(1326, "Logon failure: unknown user name or bad password")
        err.winerror = 1326
        raise err

    body = ex.fill_holes_work(
        "install",
        whatif=False,
        ldap_enum=lambda: ["FLAMINGO"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
        apply_force_install_as=boom_as,
        credman_reader=lambda: {
            "username": "EXAMPLE\\admin",
            "password": "FAKE_secret",
        },
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] == "auth_failed"
    assert row.get("detail")
    assert "1326" in row["detail"] or "logon" in row["detail"].lower()
    assert "FAKE_secret" not in str(body)


def test_fr5708_is_ipc_auth_failed_codes():
    e5 = OSError(5, "Access is denied")
    e5.winerror = 5
    e53 = OSError(53, "path")
    e53.winerror = 53
    e1326 = OSError(1326, "logon")
    e1326.winerror = 1326
    assert ex.is_ipc_auth_failed(e5) is True
    assert ex.is_ipc_auth_failed(e1326) is True
    assert ex.is_ipc_auth_failed(e53) is False
