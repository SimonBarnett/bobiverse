"""FR #8126: GHOST/RELEASE after 001 via temp nick when recover is pending."""
from __future__ import annotations

import argparse
import threading
from pathlib import Path

import irc_agent


def _client(tmp_path: Path) -> irc_agent.Client:
    args = argparse.Namespace(
        host="127.0.0.1",
        port=6697,
        nick="Bob-testbox",
        realname="bob-ear",
        password="",
        channel="#testbox",
        home=str(tmp_path),
        chair=False,
        hello="",
        announce_key=False,
        once=False,
        debug=False,
        install_root="",
    )
    c = irc_agent.Client.__new__(irc_agent.Client)
    c.args = args
    c.home = Path(tmp_path)
    c.original_nick = "Bob-testbox"
    c.live_nick = "Bob-testbox"
    c.channels = ["#testbox"]
    c.stop = threading.Event()
    c.dead = threading.Event()
    c.joined = threading.Event()
    c.ready = threading.Event()
    c.lock = threading.Lock()
    c.debug = None
    c.sock = object()
    c._nick_recover_pending = False
    c._nickname_reserved = False
    return c


def test_fr8126_registration_uses_temp_nick_when_recover_pending():
    c = _client(Path("."))
    c._nick_recover_pending = True
    assert c._nick_for_registration() == "Bob-testbox_r"
    c._nick_recover_pending = False
    assert c._nick_for_registration() == "Bob-testbox"


def test_fr8126_reserved_abort_skipped_under_temp_nick():
    c = _client(Path("."))
    c._nick_recover_pending = True
    c._nickname_reserved = True
    c.live_nick = "Bob-testbox_r"
    assert c._should_abort_nickname_reserved() is False
    c.live_nick = "Bob-testbox"
    assert c._should_abort_nickname_reserved() is True


def test_fr8126_following_attempt_sends_ghost_after_001(tmp_path):
    """Reserved-abort leaves pending; next attempt (post-001) must send GHOST."""
    c = _client(tmp_path)
    (tmp_path / "nickserv.password").write_text("FAKE_NS_PW\n", encoding="utf-8")
    # Simulate prior abort.
    c._nick_recover_pending = True
    c._nickname_reserved = True
    # Next session: register as temp, reach 001, then recover.
    c.live_nick = c._nick_for_registration()
    assert c.live_nick == "Bob-testbox_r"
    assert c._should_abort_nickname_reserved() is False
    c.ready.set()
    sent: list[str] = []

    def _capture(line: str) -> None:
        sent.append(line)

    c.send = _capture  # type: ignore[method-assign]
    c._maybe_recover_own_nick()
    ghost = [x for x in sent if x.upper().startswith("PRIVMSG NICKSERV :GHOST ")]
    release = [x for x in sent if x.upper().startswith("PRIVMSG NICKSERV :RELEASE ")]
    nick = [x for x in sent if x == "NICK Bob-testbox"]
    assert len(ghost) == 1
    assert "Bob-testbox" in ghost[0]
    assert "FAKE_NS_PW" in ghost[0]
    assert len(release) == 1
    assert nick == ["NICK Bob-testbox"]
    assert c.live_nick == "Bob-testbox"
    assert c._nick_recover_pending is False
    assert c._nickname_reserved is False


def test_fr8126_ghost_deferred_before_001(tmp_path):
    c = _client(tmp_path)
    (tmp_path / "nickserv.password").write_text("FAKE_NS_PW\n", encoding="utf-8")
    c._nick_recover_pending = True
    sent: list[str] = []
    c.send = sent.append  # type: ignore[method-assign]
    # ready not set
    c._maybe_recover_own_nick()
    assert sent == []
    assert c._nick_recover_pending is True
