"""FR #6282: git-claim handler faults must not kill the IRC reader.

MarchHare: AttributeError on gitclaim.shop_line_resets_bored_clock (and an
unlogged TypeError) ended the ear session every ~60s. Requirements:
- dispatch boundary catches handler exceptions, logs full traceback, continues
- shop_line_resets_bored_clock contract present (or safe fallback)
- startup fails loudly when the frozen/disk gitclaim contract is missing
- gitclaim must not be InstallRoot-overlayed (stale disk shadow)
Fixtures use FAKE_ only. Do not touch FR #6274 xAI acquisition.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
import irc_agent  # noqa: E402
import gitclaim  # noqa: E402


def test_fr6282_gitclaim_ships_shop_line_resets_bored_clock():
    assert callable(getattr(gitclaim, "shop_line_resets_bored_clock", None))
    assert gitclaim.shop_line_resets_bored_clock("DONE FR x/y#1 https://example.test/p/1")
    assert gitclaim.shop_line_resets_bored_clock("ACK MRB x/y#2")
    assert not gitclaim.shop_line_resets_bored_clock("!bored")


def test_fr6282_safe_helper_survives_missing_attr(monkeypatch):
    monkeypatch.delattr(irc_agent.gitclaim, "shop_line_resets_bored_clock", raising=False)
    assert irc_agent.safe_shop_line_resets_bored_clock("DONE FR x/y#1 https://example.test")
    assert not irc_agent.safe_shop_line_resets_bored_clock("hello")


def test_fr6282_call_handler_logs_traceback_and_continues(monkeypatch):
    logged: list[str] = []

    def capture(msg: str) -> None:
        logged.append(str(msg))

    monkeypatch.setattr(irc_agent, "info", capture)

    class Boom:
        def handle_privmsg(self, *a, **k):
            raise AttributeError(
                "module 'gitclaim' has no attribute 'shop_line_resets_bored_clock'"
            )

    agent = Boom()
    # Bind helper from module onto a bare instance
    out = irc_agent.Client._call_handler(
        agent, "handle_privmsg", agent.handle_privmsg, "n!u@h", "#shop", "DONE FR x/y#1"
    )
    assert out is None
    blob = "\\n".join(logged)
    assert "handler=handle_privmsg" in blob
    assert "AttributeError" in blob
    assert "shop_line_resets_bored_clock" in blob
    assert "Traceback" in blob or "File " in blob


def test_fr6282_call_handler_logs_typeerror_stack(monkeypatch):
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))

    class Boom:
        def handle_privmsg(self, *a, **k):
            raise TypeError("note_worker_activity() missing arg")

    agent = Boom()
    irc_agent.Client._call_handler(
        agent, "handle_privmsg", agent.handle_privmsg, "n!u@h", "#shop", "hi"
    )
    blob = "\\n".join(logged)
    assert "TypeError" in blob
    assert "handler=handle_privmsg" in blob


def test_fr6282_assert_gitclaim_contract_ok():
    irc_agent.assert_ear_gitclaim_contract(gitclaim)


def test_fr6282_assert_gitclaim_contract_fails_loud_when_missing():
    stub = types.ModuleType("gitclaim_stub")
    # deliberately omit shop_line_resets_bored_clock
    stub.note_worker_activity = lambda *a, **k: None
    stub.worker_shop_channel = lambda *a, **k: "#x"
    try:
        irc_agent.assert_ear_gitclaim_contract(stub)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "shop_line_resets_bored_clock" in str(exc)
        assert "FR #6282" in str(exc)
    assert raised


def test_fr6282_gitclaim_not_in_frozen_script_overlay():
    assert "gitclaim" not in irc_agent.FROZEN_SCRIPT_OVERLAY
    src = Path(irc_agent.__file__).read_text(encoding="utf-8")
    assert "def _call_handler" in src
    assert "assert_ear_gitclaim_contract" in src
    # PRIVMSG dispatch must go through _call_handler (never bare handle_privmsg)
    i = src.index("if cmd == \"PRIVMSG\" and \" :\" in wire:")
    window = src[i : i + 280]
    assert "_call_handler" in window
    assert "self.handle_privmsg(" not in window.replace(
        "_call_handler(\"handle_privmsg\", self.handle_privmsg", ""
    )


def test_fr6282_maybe_git_claim_activity_fault_isolated(monkeypatch, tmp_path):
    """note_worker_activity TypeError must not escape _maybe_git_claim."""
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))

    def boom(*a, **k):
        raise TypeError("simulated activity TypeError")

    monkeypatch.setattr(irc_agent.gitclaim, "note_worker_activity", boom)
    monkeypatch.setattr(
        irc_agent.gitclaim, "worker_shop_channel", lambda nick: "#flamingo"
    )
    monkeypatch.setattr(
        irc_agent.bobreport, "normalize_channel", lambda c: c
    )

    class FakeArgs:
        chair = False

    class Agent:
        args = FakeArgs()
        original_nick = "Bob-flamingo"
        home = tmp_path
        def _joined_channel(self, target):
            return True

    agent = Agent()
    # Should not raise
    result = irc_agent.Client._maybe_git_claim(
        agent, "flamingo-1", "#flamingo", "PRIVMSG noise"
    )
    assert result is False
    assert any("TypeError" in x or "activity" in x.lower() for x in logged)
