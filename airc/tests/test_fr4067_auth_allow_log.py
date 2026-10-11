"""FR #4067: symmetric auth-allow audit log for authorised shell/job/pipe."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import airc_console as ac
import airc_console_service as svc
from airc_auth_helpers import member_map, ops_auth


class _StubJobs:
    def handle_async(self, nick, verb, kv):  # noqa: ANN001
        self.last = (nick, verb, kv)


class _StubShell:
    def start(self, nick, cmd):  # noqa: ANN001
        self.last = (nick, cmd)


def _core(*, members=None, nick="tm_console", shell=False, jobs=True):
    m = members or member_map("simon", channel="#tm")
    auth = ac.AuthPolicy(members=m, self_nicks={nick})
    kwargs = {"machine": "tm", "auth": auth, "nick": nick}
    if jobs:
        kwargs["job_protocol"] = _StubJobs()
    if shell:
        kwargs["shell_runner"] = _StubShell()
        kwargs["job_protocol"] = None
    core = ac.AircConsoleCore(**kwargs)
    core.channel = m.channel
    return core


def test_chan_priv_mode_picks_highest_q_a_o_h():
    m = ac.ChannelMemberMap(channel="#ctrl")
    m.apply_names("~@%owner @%both %hop @op &admin plain +voice")
    m.mark_synced()
    assert m.chan_priv_mode("owner") == "+q"
    assert m.chan_priv_mode("admin") == "+a"
    assert m.chan_priv_mode("both") == "+o"  # @ beats %
    assert m.chan_priv_mode("op") == "+o"
    assert m.chan_priv_mode("hop") == "+h"
    assert m.chan_priv_mode("plain") is None
    assert m.chan_priv_mode("voice") is None
    assert m.chan_priv_mode("missing") is None
    assert m.has_chan_priv("hop") is True
    assert m.has_chan_priv("plain") is False


def test_allow_detail_ok_mode_channel():
    m = member_map("simon", halfops=("hop",), channel="#wonderland")
    auth = ac.AuthPolicy(members=m, self_nicks={"x_console"})
    d = auth.allow_detail("simon")
    assert d["ok"] is True
    assert d["mode"] == "+o"
    assert d["channel"] == "#wonderland"
    d2 = auth.allow_detail("hop")
    assert d2["ok"] is True and d2["mode"] == "+h"
    d3 = auth.allow_detail("stranger")
    assert d3["ok"] is False
    assert d3["mode"] is None
    assert d3["channel"] == "#wonderland"


def test_deny_unchanged_reason_and_no_allow_fields():
    m = member_map("simon", plain=("plain",), channel="#tm")
    core = _core(members=m)
    hr = core.handle_raw(":plain!u@h PRIVMSG tm_console :STATUS")
    assert hr is not None and hr.action == "deny"
    assert hr.deny_reason == "not-op"
    assert hr.reply == "DONE exit=126 not-op"
    assert getattr(hr, "allow_mode", None) is None
    assert getattr(hr, "allow_channel", None) is None


def test_job_allow_sets_mode_channel_account_from_tag():
    m = member_map("simon", channel="#tm")
    core = _core(members=m)
    hr = core.handle_raw("@account=simon-acct :simon!u@h PRIVMSG tm_console :STATUS")
    assert hr is not None and hr.action == "job"
    assert hr.allow_mode == "+o"
    assert hr.allow_channel == "#tm"
    assert hr.allow_account == "simon-acct"


def test_shell_and_pipe_allow_meta():
    m = member_map(halfops=("hop",), channel="#ctrl")
    core = _core(members=m, shell=True, jobs=False)
    hr = core.handle_raw(":hop!u@h PRIVMSG tm_console :Get-Date")
    assert hr is not None and hr.action == "shell"
    assert hr.allow_mode == "+h"
    assert hr.allow_channel == "#ctrl"

    auth = ops_auth("owner", channel="#ctrl")
    # owner with ~ prefix
    auth.members = member_map(channel="#ctrl")
    auth.members.apply_names("~owner")
    auth.members.mark_synced()
    core2 = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", sessions=ac.ConsoleSessionManager()
    )
    # Force legacy pipe path (no shell_runner, no job_protocol).
    core2.shell_runner = None
    core2.job_protocol = None
    core2.channel = "#ctrl"
    # pipe needs sessions.pipe — stub it
    core2.sessions = MagicMock()
    hr2 = core2.handle_raw(":owner!u@h PRIVMSG tm_console :echo hi")
    assert hr2 is not None and hr2.action == "pipe"
    assert hr2.allow_mode == "+q"
    assert hr2.allow_channel == "#ctrl"


def test_format_auth_allow_log_pin():
    line = ac.format_auth_allow_log(
        nick="slab-op",
        account=None,
        channel="#win-mpre8vi4u6u",
        mode="+o",
        action="shell",
    )
    assert line == (
        "auth-allow nick=slab-op account=- channel=#win-mpre8vi4u6u mode=+o action=shell"
    )
    line2 = ac.format_auth_allow_log(
        nick="hop", account="acct1", channel="#tm", mode="+h", action="job"
    )
    assert line2 == "auth-allow nick=hop account=acct1 channel=#tm mode=+h action=job"


def test_service_dispatch_logs_auth_allow(capsys, monkeypatch):
    """Pin service _dispatch allow path to auth-allow (no live IRC)."""
    logs: list[str] = []

    def _capture(msg: str) -> None:
        logs.append(msg)

    monkeypatch.setattr(svc, "info", _capture)

    hr = ac.HandleResult(
        action="shell",
        nick="slab-op",
        allow_mode="+o",
        allow_account=None,
        allow_channel="#win-mpre8vi4u6u",
    )
    # Minimal service stand-in: call the shared helper the service uses.
    svc.log_auth_allow(hr)
    assert logs == [
        "auth-allow nick=slab-op account=- channel=#win-mpre8vi4u6u mode=+o action=shell"
    ]

    logs.clear()
    hr2 = ac.HandleResult(
        action="job",
        nick="slab-hop",
        allow_mode="+h",
        allow_account="hop-acct",
        allow_channel="#tm",
    )
    svc.log_auth_allow(hr2)
    assert logs == [
        "auth-allow nick=slab-hop account=hop-acct channel=#tm mode=+h action=job"
    ]

    # Deny path string shape unchanged (pin source).
    text = Path(svc.__file__).read_text(encoding="utf-8")
    assert "auth-deny nick={hr.nick} account={acct or '-'} reason={reason}" in text
    assert "log_auth_allow(hr)" in text
