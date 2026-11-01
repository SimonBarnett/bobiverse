"""FR #5708: CredMan net use must not map host_down (53/67) to auth_failed."""
from __future__ import annotations

from types import SimpleNamespace

import airc_extension as ex


def test_fr5708_parse_net_system_error():
    text = "System error 53 has occurred.\n\nThe network path was not found.\n"
    assert ex.parse_net_use_system_error(text) == 53
    assert ex.parse_net_use_system_error("System error 1326 has occurred.") == 1326
    assert ex.parse_net_use_system_error("System error 1219 has occurred.") == 1219
    assert ex.parse_net_use_system_error("") is None


def test_fr5708_raise_net_use_preserves_winerror_53():
    p = SimpleNamespace(returncode=2, stdout="", stderr="System error 53 has occurred.\nThe network path was not found.\n")
    try:
        ex.raise_net_use_ipc_error(p)
        assert False, "expected OSError"
    except OSError as exc:
        assert int(getattr(exc, "winerror", 0) or getattr(exc, "errno", 0) or 0) == 53
        assert "credman-ipc-failed" not in str(exc).lower() or "53" in str(exc)
        assert "network path" in str(exc).lower() or "53" in str(exc)
        assert not ex.is_access_denied(exc)


def test_fr5708_raise_net_use_1326_is_auth():
    p = SimpleNamespace(
        returncode=2,
        stdout="System error 1326 has occurred.\nLogon failure: unknown user name or bad password.\n",
        stderr="",
    )
    try:
        ex.raise_net_use_ipc_error(p)
        assert False, "expected OSError"
    except OSError as exc:
        assert int(getattr(exc, "winerror", 0) or getattr(exc, "errno", 0) or 0) == 1326
        assert ex.is_net_use_auth_failure(exc)


def test_fr5708_classify_credman_ipc_host_down():
    exc = OSError(53, "The network path was not found")
    out = ex.classify_credman_ipc_error(exc)
    assert out["error"] == "host_down"
    assert "53" in (out.get("detail") or "") or "network path" in (out.get("detail") or "").lower()


def test_fr5708_classify_credman_ipc_auth_failed():
    for code, msg in (
        (5, "Access is denied"),
        (1326, "Logon failure: unknown user name or bad password"),
    ):
        out = ex.classify_credman_ipc_error(OSError(code, msg))
        assert out["error"] == "auth_failed", (code, out)
        assert out.get("detail")


def test_fr5708_classify_credman_ipc_conflict():
    out = ex.classify_credman_ipc_error(
        OSError(1219, "Multiple connections to a server or shared resource by the same user")
    )
    assert out["error"] == "conflicting_session"
    assert out.get("detail")


def test_fr5708_credman_identity_net53_not_auth_failed():
    """Repro: identity=credman + net use 53 must be host_down with detail."""

    def boom_as(host, product, value, username, password):
        raise OSError(53, "The network path was not found")

    body = ex.fill_holes_work(
        "install",
        whatif=False,
        ldap_enum=lambda: ["REDQUEEN"],
        ping_host=lambda _h: True,
        tcp_probe=lambda *_a, **_k: False,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(
            PermissionError(5, "Access is denied")
        ),
        apply_force_install_as=boom_as,
        credman_reader=lambda: {
            "username": r"WONDERLAND\Administrator",
            "password": "FAKE_secret",
        },
        # Force CredMan identity first (passed empty, credman present).
        passed_cred=None,
        passed_requested=False,
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] == "host_down"
    assert row["error"] != "auth_failed"
    assert row.get("detail")
    blob = str(body)
    assert "FAKE_secret" not in blob


def test_fr5708_credman_identity_auth_keeps_detail():
    def boom_as(host, product, value, username, password):
        raise OSError(1326, "Logon failure: unknown user name or bad password")

    body = ex.fill_holes_work(
        "install",
        whatif=False,
        ldap_enum=lambda: ["FLAMINGO"],
        ping_host=lambda _h: True,
        tcp_probe=lambda *_a, **_k: True,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(
            PermissionError(5, "Access is denied")
        ),
        apply_force_install_as=boom_as,
        credman_reader=lambda: {
            "username": r"WONDERLAND\Administrator",
            "password": "FAKE_secret",
        },
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] == "auth_failed"
    assert row.get("detail")
    assert "FAKE_secret" not in str(body)


def test_fr5708_default_apply_as_uses_classifier(monkeypatch):
    import shutil
    import subprocess

    class P:
        returncode = 2
        stdout = ""
        stderr = "System error 53 has occurred.\nThe network path was not found.\n"

    def fake_run(cmd, **kw):
        if len(cmd) >= 2 and str(cmd[1]).lower() == "use" and "/delete" not in [
            str(x).lower() for x in cmd
        ]:
            return P()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(shutil, "which", lambda _n: "net")
    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        ex.default_apply_force_install_as("REDQUEEN", "chrome", "x", "u", "FAKE_pw")
        assert False, "expected OSError"
    except OSError as exc:
        assert int(getattr(exc, "winerror", 0) or getattr(exc, "errno", 0) or 0) == 53
        assert not ex.is_access_denied(exc)
        assert "FAKE_pw" not in str(exc)
