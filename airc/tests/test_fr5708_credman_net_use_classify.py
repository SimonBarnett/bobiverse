"""FR #5708: classify CredMan IPC failures by Windows system error."""
from __future__ import annotations

import subprocess

import pytest

import airc_extension as ex


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected"),
    [
        ("", "System error 53 has occurred.", 53),
        ("NET HELPMSG 1219", "", 1219),
        ("", "Systemfehler 1326 ist aufgetreten.", 1326),
        ("", "2250", 2250),
        ("", "", None),
    ],
)
def test_fr5708_parse_net_use_error_code(stdout, stderr, expected):
    assert ex._net_use_error_code(stdout, stderr) == expected


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("System error 53 has occurred.", 53),
        ("System error 67 has occurred.", 67),
        ("System error 5 has occurred.", 5),
        ("System error 1219 has occurred.", 1219),
        ("System error 1326 has occurred.", 1326),
    ],
)
def test_fr5708_apply_as_preserves_code_without_output_or_password(
    monkeypatch, stderr, expected
):
    calls = []

    class Result:
        returncode = 1
        stdout = ""

    def run(args, **_kwargs):
        calls.append(args)
        result = Result()
        result.stderr = stderr
        return result

    monkeypatch.setattr("shutil.which", lambda _name: "net.exe")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OSError) as caught:
        ex.default_apply_force_install_as(
            "host", "chrome", "value", "user", "FAKE_PASSWORD"
        )
    assert caught.value.errno == expected
    assert str(expected) in str(caught.value)
    assert "FAKE_PASSWORD" not in str(caught.value)
    assert "System error" not in str(caught.value)
    assert len(calls) == 2
    assert calls[1][2:] == [r"\\host\IPC$", "/delete", "/y"]


def test_fr5708_unknown_error_and_missing_net_are_not_auth_failures(monkeypatch):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "failure without a system error"

    monkeypatch.setattr("shutil.which", lambda _name: "net.exe")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Result())
    with pytest.raises(OSError) as unknown:
        ex.default_apply_force_install_as("host", "chrome", "value", "user", "pw")
    assert unknown.value.errno is None
    assert not ex.is_access_denied(unknown.value)

    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(OSError) as missing:
        ex.default_apply_force_install_as("host", "chrome", "value", "user", "pw")
    assert not ex.is_access_denied(missing.value)


def test_fr5708_timeout_is_sanitized_and_cleanup_error_does_not_mask(monkeypatch):
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(args, 20)
        raise OSError("cleanup failed")

    monkeypatch.setattr("shutil.which", lambda _name: "net.exe")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(TimeoutError) as caught:
        ex.default_apply_force_install_as(
            "host", "chrome", "value", "user", "FAKE_PASSWORD"
        )
    assert "timed out" in str(caught.value)
    assert "FAKE_PASSWORD" not in str(caught.value)
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("error_code", "icmp", "smb", "expected"),
    [
        (53, False, False, "host_down"),
        (53, True, False, "smb_blocked"),
        (67, False, False, "host_down"),
        (5, True, True, "auth_failed"),
        (1326, True, True, "auth_failed"),
        (1219, True, True, "session_conflict"),
    ],
)
def test_fr5708_credman_failures_keep_classification_and_identity(
    error_code, icmp, smb, expected
):
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["target"],
        ping_host=lambda _host: icmp,
        is_windows_host=lambda _host: True,
        tcp_probe=lambda *_args: smb,
        apply_force_install_as=lambda *_args: (_ for _ in ()).throw(
            OSError(error_code, f"system error {error_code}")
        ),
        credman_reader=lambda: {"username": "DOMAIN\\admin", "password": "FAKE_pw"},
    )
    row = body["hosts"][0]
    assert row["error"] == expected
    assert row["identity"] == "credman"
    assert row["account"] == "DOMAIN\\admin"
    assert str(error_code) in row["detail"]
    assert "FAKE_pw" not in str(body)


def test_fr5708_system_to_credman_retry_keeps_host_down_detail():
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["target"],
        ping_host=lambda _host: False,
        is_windows_host=lambda _host: True,
        tcp_probe=lambda *_args: False,
        apply_force_install=lambda *_args: (_ for _ in ()).throw(
            PermissionError("Access is denied")
        ),
        apply_force_install_as=lambda *_args: (_ for _ in ()).throw(
            OSError(53, "system error 53")
        ),
        credman_reader=lambda: {"username": "DOMAIN\\admin", "password": "FAKE_pw"},
    )
    row = body["hosts"][0]
    assert row["error"] == "host_down"
    assert row["identity"] == "credman"
    assert row["account"] == "DOMAIN\\admin"
    assert "53" in row["detail"]
    assert "FAKE_pw" not in str(body)
