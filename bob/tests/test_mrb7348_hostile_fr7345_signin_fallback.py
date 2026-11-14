"""MRB #7348 hostile: FR #7345 prompt kill must fall back (not EXIT_OK recycle)."""
from __future__ import annotations

from types import SimpleNamespace

import bob_worker as bw


class _FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid
        self._alive = True

    def poll(self):
        return None if self._alive else 0


def test_mrb7348_prompt_fallback_prefers_cursor():
    d = bw.decision_after_grok_signin_prompt(
        bw.Fuel(40, 10, 50, "available"),
        r"C:\c\agent.cmd",
        None,
    )
    assert d.kind == "cursor"
    assert "xai-auth-expired" in d.reason


def test_mrb7348_prompt_fallback_exits_when_no_fuel():
    d = bw.decision_after_grok_signin_prompt(
        bw.Fuel(0, 0, 0, "exhausted"),
        None,
        None,
    )
    assert d.kind == "xai-auth-expired"


def test_mrb7348_supervisor_prompt_falls_back_to_cursor(monkeypatch):
    """Kill + Cursor start; never shutdown EXIT_OK."""
    logs: list[str] = []
    kills: list[int] = []
    starts: list[str] = []
    shut: list[tuple] = []

    irc = SimpleNamespace(shop="#flamingo", say=lambda *_a, **_k: None)
    relay = SimpleNamespace(
        set_target=lambda *_a, **_k: None,
        last_unacked="",
        hold=lambda *_a, **_k: None,
        deliver=lambda *_a, **_k: None,
    )
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\g\agent.exe",
        cwd=r"C:\ai\bob\worker",
        machine="flamingo",
        nick="flamingo-1",
        run_dir=r"C:\tmp\mrb7348",
        irc=irc,
        relay=relay,
        log=logs.append,
        install_root=r"C:\ai\bob",
        kill=lambda pid: kills.append(pid) or True,
        spawn=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no spawn")),
    )
    proc = _FakeProc(777)
    sup.proc = proc

    monkeypatch.setattr(bw, "read_fuel", lambda *_a, **_k: bw.Fuel(40, 10, 50, "available"))
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda: r"C:\c\agent.cmd")
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda: None)

    def fake_start(note=""):
        starts.append(note)
        return True

    monkeypatch.setattr(sup, "start_agent", fake_start)
    monkeypatch.setattr(sup, "shutdown", lambda why, code: shut.append((why, code)))

    sup._fallback_after_grok_signin_prompt(proc)

    assert kills == [777]
    assert 777 in sup._expected_exit
    assert starts and "sign-in prompt" in starts[0]
    assert sup.kind == "cursor"
    assert sup.exe == r"C:\c\agent.cmd"
    assert shut == []
    assert bw.EXIT_OK not in [c for _w, c in shut]


def test_mrb7348_supervisor_prompt_exits_xai_auth_when_no_cursor(monkeypatch):
    shut: list[tuple] = []
    irc = SimpleNamespace(shop="#flamingo", say=lambda *_a, **_k: None)
    relay = SimpleNamespace(set_target=lambda *_a, **_k: None, last_unacked="")
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\g\agent.exe",
        cwd=r"C:\ai\bob\worker",
        machine="flamingo",
        nick="flamingo-1",
        run_dir=r"C:\tmp\mrb7348b",
        irc=irc,
        relay=relay,
        log=lambda _m: None,
        install_root=r"C:\ai\bob",
        kill=lambda _pid: True,
    )
    proc = _FakeProc(888)
    sup.proc = proc
    monkeypatch.setattr(bw, "read_fuel", lambda *_a, **_k: bw.Fuel(0, 0, 0, "exhausted"))
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda: None)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda: None)
    monkeypatch.setattr(sup, "shutdown", lambda why, code: shut.append((why, code)))

    sup._fallback_after_grok_signin_prompt(proc)

    assert shut == [("xai-auth-expired-prompt", bw.EXIT_XAI_AUTH_EXPIRED)]


def test_mrb7348_guard_invokes_fallback_not_bare_kill():
    import inspect

    text = inspect.getsource(bw.Supervisor._start_grok_signin_guard)
    assert "_fallback_after_grok_signin_prompt" in text
    # Guard thread must not bare-kill without the fallback path.
    assert "kill_tree" not in text
    fb = inspect.getsource(bw.Supervisor._fallback_after_grok_signin_prompt)
    assert "decision_after_grok_signin_prompt" in fb
    assert "EXIT_XAI_AUTH_EXPIRED" in fb
    assert "shutdown(" in fb and "EXIT_XAI_AUTH_EXPIRED)" in fb
    assert "EXIT_OK)" not in fb
