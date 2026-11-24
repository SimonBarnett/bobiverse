"""FR #9804: .NET IrcSeat TLS + JOIN shop gate before spawn.

Pins: SslStream transport, connect_with_retries, Ergo password search paths
(never log secret), FakeIrcTransport hermetic tests, StartAgentGate closed
without JOIN, Program --self-test-irc, CI runs self-test after publish.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-worker-net.yml"
DOCS = ROOT / "bob" / "docs" / "bob-worker-net.md"
DOCS_WORKER = ROOT / "bob" / "docs" / "bob-worker.md"
PROGRAM = ROOT / "bob" / "worker" / "dotnet" / "Program.cs"
IRC_SEAT = ROOT / "bob" / "worker" / "dotnet" / "IrcSeat.cs"
SSL = ROOT / "bob" / "worker" / "dotnet" / "SslStreamIrcTransport.cs"
FAKE = ROOT / "bob" / "worker" / "dotnet" / "FakeIrcTransport.cs"
ERGO = ROOT / "bob" / "worker" / "dotnet" / "ErgoPassword.cs"
TRANSPORT = ROOT / "bob" / "worker" / "dotnet" / "IIrcTransport.cs"


def _t(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fr9804_irc_seat_files_exist():
    for p in (IRC_SEAT, SSL, FAKE, ERGO, TRANSPORT):
        assert p.is_file(), f"missing {p.relative_to(ROOT)}"


def test_fr9804_irc_seat_join_gate_and_retries():
    text = _t(IRC_SEAT)
    assert "CanStartAgent" in text
    assert "IsRegistered" in text
    assert "IsJoined" in text
    assert "ConnectWithRetries" in text
    assert "StartAgentGate" in text
    assert "EnsureOpen" in text
    assert "JOIN" in text
    assert "PASS " in text or '"PASS "' in text or "PASS \" +" in text or 'PASS "' in text
    # Password must never be logged via the seat log path.
    assert "Never log Password" in text or "never logged" in text.lower()
    assert "start_agent gate" in text.lower() or "StartAgentGate" in text


def test_fr9804_sslstream_transport():
    text = _t(SSL)
    assert "SslStream" in text
    assert "TcpClient" in text
    assert "AuthenticateAsClient" in text
    assert "IIrcTransport" in text


def test_fr9804_fake_transport_for_ci():
    text = _t(FAKE)
    assert "FakeIrcTransport" in text
    assert "ArmWelcome" in text
    assert "IIrcTransport" in text
    assert "EnqueueServerLine" in text


def test_fr9804_ergo_password_paths_parity():
    text = _t(ERGO)
    assert "BOB_IRC_PASSWORD" in text
    assert "ergo.password" in text
    assert "CandidatePaths" in text
    assert ".bobiverse" in text
    assert ".grok" in text
    assert "connect.password" in text
    assert "never log" in text.lower() or "must not log" in text.lower()


def test_fr9804_program_self_test_irc():
    text = _t(PROGRAM)
    assert "--self-test-irc" in text
    assert "RunIrcSelfTest" in text
    assert "StartAgentGate" in text
    assert "FakeIrcTransport" in text
    assert "ErgoPassword" in text
    assert "secret-not-logged" in text  # fixture value asserted absent from ToString
    assert "no-JOIN" in text or "no JOIN" in text.lower() or "EnsureOpen" in text
    assert "FR #9804" in text


def test_fr9804_ci_runs_self_test_irc():
    text = _t(WF)
    assert "--self-test-irc" in text
    assert "test_fr9804_irc_seat_join_gate.py" in text
    assert "setup-dotnet@v4" in text
    assert "bob-worker-net.exe" in text


def test_fr9804_docs_irc_seat():
    docs = _t(DOCS)
    assert "FR #9804" in docs
    assert "--self-test-irc" in docs
    assert "IrcSeat" in docs or "JOIN" in docs
    assert "StartAgentGate" in docs or "CanStartAgent" in docs
    assert "SslStream" in docs
    assert "Ergo" in docs or "ergo.password" in docs
    assert "test_fr9804_irc_seat_join_gate.py" in docs
    worker = _t(DOCS_WORKER)
    assert "9804" in worker or "IrcSeat" in worker
