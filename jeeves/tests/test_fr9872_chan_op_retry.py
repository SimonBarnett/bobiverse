# -*- coding: utf-8 -*-
"""FR #9872: ChanServ/+o retry backoff; commands not gated on chair +o."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import chair_commands  # noqa: E402
import chair_oper as co  # noqa: E402
import irc_agent  # noqa: E402

DOCS = ROOT / "jeeves" / "docs" / "monitoring.md"
ADMIN = ROOT / "jeeves" / "docs" / "jeeves-admin.md"


def test_fr9872_docs_walrus_pin():
    docs = DOCS.read_text(encoding="utf-8")
    assert "9872" in docs
    assert "require_machine=walrus" in docs
    admin = ADMIN.read_text(encoding="utf-8")
    assert "9872" in admin


def test_fr9872_backoff_grows_and_caps():
    assert co.op_retry_backoff_s(0, base=15, cap=300) == 15
    assert co.op_retry_backoff_s(1, base=15, cap=300) == 30
    assert co.op_retry_backoff_s(2, base=15, cap=300) == 60
    assert co.op_retry_backoff_s(10, base=15, cap=300) == 300
    assert co.cs_sync_retry_backoff_s(0) == 30
    assert co.cs_sync_retry_backoff_s(3) >= 30


def test_fr9872_plan_dual_path_after_first_miss():
    a0 = co.plan_chan_op_recover(
        oper_ok=True, channel="#bobiverse", nick="Jeeves", attempt=0
    )
    assert [x["verb"] for x in a0] == ["SAMODE"]
    assert a0[0]["line"] == "SAMODE #bobiverse +o Jeeves"
    a1 = co.plan_chan_op_recover(
        oper_ok=True, channel="#bobiverse", nick="Jeeves", attempt=1
    )
    assert [x["verb"] for x in a1] == ["SAMODE", "CHANSERV_OP"]
    assert a1[1]["line"] == "PRIVMSG ChanServ :OP #bobiverse"
    non = co.plan_chan_op_recover(
        oper_ok=False, channel="#redqueen", nick="Jeeves", attempt=0
    )
    assert [x["verb"] for x in non] == ["CHANSERV_OP"]


def test_fr9872_commands_not_gated_on_chan_op():
    assert chair_commands.commands_require_chan_op() is False
    assert co.commands_require_chan_op() is False
    ear = chair_commands.classify("bob-redqueen", ear_machine=lambda n: "redqueen")
    mon = chair_commands.classify("monitoring")
    assert ear.ops and mon.ops
    assert chair_commands.may("status", ear)
    assert chair_commands.may("assign", ear)
    assert chair_commands.may("status", mon)
    assert chair_commands.may("assign", mon)


class _FakeChair:
    def __init__(self, home):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.live_nick = "Jeeves"
        self.channels = ["#bobiverse", "#redqueen"]
        self.sent = []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._oper_state = "ok"
        self._chan_op = {}
        self._op_try_at = {}
        self._op_fail_count = {}
        self._cs_fail_count = 0
        self._cs_collector = None
        self._cs_sent_at = 0.0
        self._cs_force = False
        self._cs_fail_at = 0.0
        self._cs_list_status = "unknown"
        self._chair_status_at = 0.0
        self._chair_status_last = ""

    def send(self, line):
        self.sent.append(line)

    def _digest_home(self):
        return self.home

    _ensure_chan_ops = irc_agent.Client._ensure_chan_ops
    _chair_status_line = irc_agent.Client._chair_status_line
    _chair_log_status = irc_agent.Client._chair_log_status
    _cs_ttl_s = irc_agent.Client._cs_ttl_s
    _maybe_chanserv_sync = irc_agent.Client._maybe_chanserv_sync


def test_fr9872_ensure_retries_with_backoff_and_dual(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logs.append(m))
    chair = _FakeChair(tmp_path)
    chair._ensure_chan_ops()
    assert "SAMODE #bobiverse +o Jeeves" in chair.sent
    assert "PRIVMSG ChanServ :OP #bobiverse" not in chair.sent
    assert chair._op_fail_count["#bobiverse"] == 1
    n = len(chair.sent)
    chair._ensure_chan_ops()  # within backoff
    assert len(chair.sent) == n
    chair._op_try_at["#bobiverse"] = time.time() - 999
    chair._op_try_at["#redqueen"] = time.time() - 999
    chair._ensure_chan_ops()
    assert "PRIVMSG ChanServ :OP #bobiverse" in chair.sent
    assert any("dual-path" in m for m in logs)


def test_fr9872_chanserv_sync_timeout_escalates(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logs.append(m))
    chair = _FakeChair(tmp_path)
    chair._cs_collector = object()
    chair._cs_sent_at = time.time() - 60
    chair._maybe_chanserv_sync()
    assert chair._cs_collector is None
    assert chair._cs_fail_count == 1
    assert any("chanserv-sync timeout" in m and "fail_count=1" in m for m in logs)
    chair._cs_fail_at = time.time()
    chair._maybe_chanserv_sync()
    assert chair._cs_collector is None
