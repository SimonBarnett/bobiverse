"""FR #5836: CRED via=irc must resolve priority-instances via install_root.

Service constructs AircConsoleCore with install_root and without
priority_allowlist_path. PRIORITY status falls back to install_root;
CRED must use the same shared resolver.
"""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_cred_irc as circ
from airc_auth_helpers import ops_auth

FAKE_USER = "Tabula"
QID = "c5836001"
TARGET = "PriorityWeb/hrs-priority-dev"
OTHER = "PriorityWeb/not-listed"


def _write_allowlist(install_root: Path) -> Path:
    cfg = install_root / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    path = cfg / "priority-instances.json"
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
    """Mirror airc_console_service: install_root set, allowlist path not injected."""
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=None,
        install_root=str(install_root),
        # intentionally omit priority_allowlist_path / priority_allowlist
    )


def test_fr5836_service_style_core_cred_irc_hello(tmp_path: Path):
    _write_allowlist(tmp_path)
    core = _service_style_core(tmp_path)
    assert core.priority_allowlist_path is None
    core.irc_cred_sessions = circ.IrcCredSessionStore()

    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    assert hr is not None
    assert hr.action == "cred"
    text = hr.reply or ""
    assert "cred-target-not-allowlisted" not in text
    assert "CRED-HELLO" in text
    assert TARGET in text


def test_fr5836_service_style_core_rejects_unknown_target(tmp_path: Path):
    _write_allowlist(tmp_path)
    core = _service_style_core(tmp_path)
    core.irc_cred_sessions = circ.IrcCredSessionStore()

    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={OTHER} via=irc"
    )
    assert hr is not None
    assert "cred-target-not-allowlisted" in (hr.reply or "")


def test_fr5836_resolved_allowlist_helper(tmp_path: Path):
    path = _write_allowlist(tmp_path)
    core = _service_style_core(tmp_path)
    resolved = core._resolved_priority_allowlist_path()
    assert resolved is not None
    assert Path(resolved).resolve() == path.resolve()
