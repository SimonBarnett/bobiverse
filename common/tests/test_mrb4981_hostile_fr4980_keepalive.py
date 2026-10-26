# MRB #4981 / FR #4980: hostile pins --- ear idle keepalive mirrors airc.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
BOB_EAR_DOC = ROOT / "bob" / "docs" / "bob-ear.md"


def test_irc_agent_has_idle_ping_dead_and_recv_timeout_env() -> None:
    src = IRC_AGENT.read_text(encoding="utf-8")
    assert "FR #4980" in src
    assert "BOB_IRC_IDLE_PING_S" in src
    assert "BOB_IRC_IDLE_DEAD_S" in src
    assert "BOB_IRC_RECV_TIMEOUT_S" in src
    assert "idle-dead" in src
    assert "def idle_ping_s()" in src
    assert "def idle_dead_s()" in src
    assert "def recv_timeout_s()" in src


def test_recv_loop_sets_socket_timeout_and_wakes_on_timeout() -> None:
    src = IRC_AGENT.read_text(encoding="utf-8")
    assert "sock.settimeout(recv_timeout_s())" in src
    assert "wake on timeout" in src or "socket.timeout" in src
    assert "_maybe_client_keepalive" in src or "client PING" in src


def test_bob_ear_docs_document_keepalive_and_recovery() -> None:
    doc = BOB_EAR_DOC.read_text(encoding="utf-8")
    assert "FR #4980" in doc
    assert "BOB_IRC_IDLE_PING_S" in doc
    assert "BOB_IRC_IDLE_DEAD_S" in doc
    assert "idle-dead" in doc
    assert "Restart-BobEar" in doc or "Restart-Service ircBob" in doc
