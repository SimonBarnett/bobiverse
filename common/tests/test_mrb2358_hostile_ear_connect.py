"""MRB #2358 hostile: FR #2351 TLS fail logs + soft identity + --once contract."""
from __future__ import annotations

import argparse
import ssl
from pathlib import Path
from unittest import mock

import pytest

import irc_agent


def _args(home: Path, **kw):
    base = dict(
        nick="ear-test-mrb2358",
        channel="#bob-ear-uat-2351",
        home=str(home),
        host="127.0.0.1",
        port=1,
        password="",
        realname="test",
        outbox="",
        hello="",
        announce_key=False,
        once=True,
        chair=False,
        auto_nick=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_mrb2358_tls_fail_writes_irc_log(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("BOB_IRC_DEBUG", "1")
    monkeypatch.setenv("BOB_HOME", str(home))
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.setenv("BOB_IRC_SKIP_PRIOR_CLEAN", "1")
    monkeypatch.setattr(irc_agent.protect, "protect_path", lambda p: None)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kw: [])

    c = irc_agent.Client(_args(home))
    assert c.debug is not None

    class Raw:
        def settimeout(self, _t):
            return None

        def close(self):
            return None

    monkeypatch.setattr(
        irc_agent.socket, "create_connection", lambda *a, **k: Raw()
    )

    def boom_wrap(self, sock, server_hostname=None):
        raise ssl.SSLError("hostile-tls")

    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", boom_wrap)
    with pytest.raises(ssl.SSLError):
        c.connect()
    body = Path(c.debug).read_text(encoding="utf-8").lower()
    assert "tcp-ok" in body
    assert "tls-fail" in body


def test_mrb2358_corrupt_identity_soft_fails(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("BOB_IRC_DEBUG", "1")
    monkeypatch.setenv("BOB_HOME", str(home))
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.setattr(irc_agent.protect, "protect_path", lambda p: None)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kw: [])
    monkeypatch.setattr(irc_agent.seal, "ident_path", lambda: home / "identity.json")
    (home / "identity.json").write_text("{}", encoding="utf-8")

    def boom():
        raise OSError("dpapi-hostile")

    monkeypatch.setattr(irc_agent.seal, "load_ident", boom)
    c = irc_agent.Client(_args(home))
    assert c.ident is None
    assert Path(c.debug).is_file()


def test_mrb2358_docs_mention_standalone_uat():
    doc = Path(irc_agent.__file__).resolve().parents[2] / "bob/docs/bob-ear.md"
    # repo layout: common/scripts -> parents[2] is repo root in worktree
    if not doc.is_file():
        doc = Path(__file__).resolve().parents[2] / "bob/docs/bob-ear.md"
    text = doc.read_text(encoding="utf-8")
    assert "2351" in text or "BOB_IRC_DEBUG" in text
    assert "--once" in text or "once" in text.lower()
