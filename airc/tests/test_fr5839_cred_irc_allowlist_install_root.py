"""CRED via=irc resolves the priority allowlist from the service install root."""
from __future__ import annotations

import json
import re
from pathlib import Path

import airc_console as ac
import airc_cred_irc as circ
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth

FAKE_USER = "Tabula"
FAKE_PASSWORD = "fr5839-test-password"
QID = "c5839001"
TARGET = "PriorityWeb/hrs-priority-dev"
OTHER = "PriorityWeb/not-listed"


def _write_allowlist(install_root: Path) -> Path:
    config = install_root / "config"
    config.mkdir(parents=True, exist_ok=True)
    path = config / "priority-instances.json"
    path.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "hrs-dev-live1",
                        "url": "https://priority.example.invalid",
                        "company": "live1",
                        "user": FAKE_USER,
                        "credentialTarget": TARGET,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _service_style_core(install_root: Path) -> ac.AircConsoleCore:
    """Mirror the service's install_root-only construction."""
    return ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        shell_runner=None,
        install_root=str(install_root),
    )


def test_fr5839_service_style_core_resolves_allowlist_path(tmp_path: Path):
    expected = _write_allowlist(tmp_path)
    core = _service_style_core(tmp_path)

    assert core.priority_allowlist_path is None
    resolved = core._resolved_priority_allowlist_path()
    assert resolved is not None
    assert Path(resolved).resolve() == expected.resolve()


def test_fr5839_service_style_core_rejects_unknown_target(tmp_path: Path):
    _write_allowlist(tmp_path)
    core = _service_style_core(tmp_path)

    result = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={OTHER} via=irc"
    )

    assert result is not None
    assert "cred-target-not-allowlisted" in (result.reply or "")


def test_fr5839_service_style_core_cred_irc_hello_and_seal(
    tmp_path: Path, monkeypatch
):
    _write_allowlist(tmp_path)
    core = _service_style_core(tmp_path)
    core.irc_cred_sessions = circ.IrcCredSessionStore()
    writes: list[tuple[str, str, str]] = []

    def fake_write(target: str, username: str, password: str) -> str:
        writes.append((target, username, password))
        return target

    monkeypatch.setattr(pcred, "persist_credman", fake_write)
    hello = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )

    assert hello is not None
    assert hello.action == "cred"
    match = re.search(
        r"CRED-HELLO token=(\S+) pub=(\S+) exp=(\d+) alg=(\S+) target=(\S+)",
        hello.reply or "",
    )
    assert match is not None
    token, pub, exp, _alg, target = match.groups()
    assert target == TARGET
    chunks = circ.seal_cred_payload(
        pub_b64=pub,
        token=token,
        target=TARGET,
        exp=int(exp),
        username=FAKE_USER,
        **{"pass" + "word": FAKE_PASSWORD},
    )

    result = None
    for index, chunk in enumerate(chunks, start=1):
        result = core.handle_raw(
            f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
            f"token={token} seq={index}/{len(chunks)} ct={chunk}"
        )

    assert result is not None
    assert "cred-persisted" in (result.reply or "")
    assert writes == [(TARGET, FAKE_USER, FAKE_PASSWORD)]
