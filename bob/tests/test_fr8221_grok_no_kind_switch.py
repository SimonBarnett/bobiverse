"""FR #8221: a seat only ever runs the kind the tray launched.

A Grok seat that hits an interactive xAI sign-in prompt (or an expired sign-in)
exits xai-auth-expired; it never falls back to Cursor/OpenCode even when free
OpenCode fuel remains. A recycled clicked-Grok seat keeps kind=grok. An OpenCode
start with an empty/unresolved model refuses before writing launch-opencode.ps1.
"""
from __future__ import annotations

from types import SimpleNamespace

import bob_worker as bw


class _FakeProc:
    def __init__(self, pid=9002):
        self.pid = pid

    def poll(self):
        return None

    def stderr_tail(self):
        return ""


def _grok_supervisor(tmp_path, **kw):
    irc = SimpleNamespace(shop="#flamingo", say=lambda *_a, **_k: None)
    relay = SimpleNamespace(
        set_target=lambda *_a, **_k: None,
        last_unacked="",
        hold=lambda *_a, **_k: None,
        deliver=lambda *_a, **_k: None,
        release_held_assigns=lambda: 0,
        close=lambda: None,
    )
    defaults = dict(
        kind="grok",
        exe=r"C:\g\agent.exe",
        cwd=r"C:\ai\bob\worker",
        machine="flamingo",
        nick="flamingo-1",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=lambda _m: None,
        install_root=r"C:\ai\bob",
        kill=lambda _pid: True,
        backoff=(0.0,),
        restart_max=3,
        restart_window_s=1800.0,
    )
    defaults.update(kw)
    return bw.Supervisor(**defaults)


def test_fr8221_decision_after_prompt_exits_xai_auth_with_cursor_and_opencode_fuel():
    d = bw.decision_after_grok_signin_prompt(
        bw.Fuel(40, 10, 50, "available", opencode_free=100),
        r"C:\c\agent.cmd",
        r"C:\o\opencode.exe",
    )
    assert d.kind == "xai-auth-expired"
    assert d.kind not in ("cursor", "opencode")


def test_fr8221_apply_xai_gate_grok_never_falls_through():
    # An automatic grok decision with an expired sign-in never falls through.
    d = bw.apply_xai_signin_gate(
        bw.Decision("grok", "automatic"),
        bw.Fuel(40, 10, 50, "available", opencode_free=100),
        r"C:\c\agent.cmd",
        r"C:\g\agent.exe",
        r"C:\o\opencode.exe",
        signin_ok=False,
    )
    assert d.kind == "xai-auth-expired"
    assert "xai-auth-expired" in d.reason


def test_fr8221_supervisor_prompt_exits_no_kind_switch(monkeypatch, tmp_path):
    shut: list[tuple] = []
    starts: list[str] = []
    posts: list[dict] = []
    sup = _grok_supervisor(tmp_path)
    proc = _FakeProc(777)
    sup.proc = proc
    monkeypatch.setattr(bw, "read_fuel", lambda *_a, **_k: bw.Fuel(40, 10, 50, "available", opencode_free=100))
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda: r"C:\c\agent.cmd")
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda: r"C:\o\opencode.exe")
    monkeypatch.setattr(bw, "_http_post_json", lambda url, payload, **kw: posts.append(payload) or True)
    monkeypatch.setattr(sup, "shutdown", lambda why, code: shut.append((why, code)))
    sup.start_agent = lambda note="": starts.append(note) or True

    sup._fallback_after_grok_signin_prompt(proc)

    assert starts == []              # never launched Cursor or OpenCode
    assert sup.kind == "grok"        # kind never switched
    assert sup.exe == r"C:\g\agent.exe"
    assert shut == [("xai-auth-expired-prompt", bw.EXIT_XAI_AUTH_EXPIRED)]
    assert posts                     # reported to the digest
    assert posts[0].get("state") == "needs_sign_in"


def test_fr8221_supervisor_reports_login_expired_once(monkeypatch, tmp_path):
    posts: list[dict] = []
    sup = _grok_supervisor(tmp_path)
    monkeypatch.setattr(bw, "_http_post_json", lambda url, payload, **kw: posts.append(payload) or True)
    sup._report_grok_login_expired()
    sup._report_grok_login_expired()
    assert len(posts) == 1
    assert posts[0].get("state") == "needs_sign_in"


def test_fr8221_restart_preserves_grok_kind(monkeypatch, tmp_path):
    starts: list[str] = []
    posts: list[dict] = []
    sup = _grok_supervisor(tmp_path)
    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(bw, "report_agent_cli_nonzero_exit", lambda **kw: posts.append(kw) or {"ok": True})
    sup.proc = _FakeProc(777)
    sup.start_agent = lambda note="": starts.append(note) or True
    sup.restart_agent("not-responding")

    assert sup.kind == "grok"
    assert sup.exe == r"C:\g\agent.exe"
    assert starts  # recycled as the same kind, never switched to Cursor/OpenCode


def test_fr8221_start_agent_refuses_empty_opencode_model(monkeypatch):
    """Refuse only when launch_selected_model itself is empty (MRB #8232)."""
    import worker_start_model as wsm

    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.setattr(wsm, "launch_selected_model", lambda *a, **k: "")
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.machine = "flamingo"
    sup.log = lambda *_a, **_k: None
    reported: list[dict] = []
    monkeypatch.setattr(bw, "report_seat_start_refusal", lambda **kw: reported.append(kw) or {"ok": True})
    assert sup.start_agent() is False
    assert reported
    assert reported[0].get("kind") == "opencode"


def test_mrb8232_empty_env_still_starts_when_free_default_resolves(monkeypatch):
    """FR #8220: empty parent env is not a refusal when the free default resolves."""
    import worker_start_model as wsm

    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.setattr(
        wsm, "launch_selected_model", lambda *a, **k: "opencode/deepseek-v4.1-flash-free"
    )
    monkeypatch.setattr(bw, "probe_gh_auth", lambda *_a, **_k: (True, "gh auth missing"))
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.log = lambda *_a, **_k: None
    reported: list[dict] = []
    monkeypatch.setattr(bw, "report_seat_start_refusal", lambda **kw: reported.append(kw) or {"ok": True})
    assert sup.start_agent() is False
    assert reported == []


def test_fr8221_start_agent_proceeds_with_resolved_opencode_model(monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "opencode/deepseek-v4.1-flash-free")
    monkeypatch.setattr(bw, "probe_gh_auth", lambda *_a, **_k: (True, "gh auth missing"))
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.log = lambda *_a, **_k: None
    # With a resolved model the empty-model guard does not fire; the seat reaches
    # the gh-auth probe instead (and refuses there in this offline harness).
    assert sup.start_agent() is False
