"""FR #9016: fuel-quit must exit; no fuel-hold zombies; no revive after free=0."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import bob_worker as bw

ROOT = Path(__file__).resolve().parents[2]


def test_fr9016_quit_removes_before_dialog_then_shutdown():
    """Source order: worker-remove → dialog → shutdown (MessageBox must not block remove)."""
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    fn = src.index("def _quit_after_out_of_fuel")
    body = src[fn : src.index("\n    def ", fn + 10)]
    remove = body.index("post_digest_worker_remove")
    dialog = body.index("show_out_of_fuel_dialog")
    shutdown = body.index('self.shutdown("fuel-exhausted"')
    assert remove < dialog < shutdown


def test_fr9016_messagebox_is_daemon_threaded():
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    fn = src.index("def show_out_of_fuel_dialog")
    body = src[fn : src.index("\ndef ", fn + 10)]
    assert 'name="out-of-fuel-dialog"' in body
    assert "daemon=True" in body
    assert "th.join(" in body


def test_fr9016_quit_completes_with_slow_dialog(monkeypatch):
    """Quit path finishes even when dialog show_fn is slow (daemon + join bound)."""
    logs: list[str] = []
    removed: list[dict] = []
    shut: list[tuple[str, int]] = []
    gate = threading.Event()

    def _slow(_text: str, _title: str) -> None:
        gate.wait(timeout=30.0)

    monkeypatch.setattr(
        bw,
        "post_digest_worker_remove",
        lambda **kwargs: removed.append(dict(kwargs)) or True,
    )

    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.log = logs.append
    sup.nick = "redqueen-13608"
    sup.machine = "redqueen"
    sup.kind = "opencode"
    sup.proc = None
    sup.base_env = {"BOB_WORKER_OUT_OF_FUEL_QUIT": "1", "BOB_WORKER_FUEL_DIALOG": "1"}
    sup._out_of_fuel_quit_started = False
    # Inject show_fn via the dialog helper's show_fn parameter path.
    # Patch show_out_of_fuel_dialog to use threaded show like production.
    def _dialog(**kwargs):
        show_fn = kwargs.get("show_fn") or _slow
        text = "t"
        title = "x"

        def _box():
            try:
                show_fn(text, title)
            except Exception:
                pass

        th = threading.Thread(target=_box, name="out-of-fuel-dialog", daemon=True)
        th.start()
        th.join(0.2)
        return True

    monkeypatch.setattr(bw, "show_out_of_fuel_dialog", _dialog)
    monkeypatch.setattr(bw, "out_of_fuel_quit_enabled", lambda env=None: True)
    # Keep pool bits cheap
    monkeypatch.setattr(
        bw.Supervisor,
        "_out_of_fuel_dialog_pool_bits",
        lambda self, evidence="": ("opencode_free", "free=0 go=0", ""),
    )
    sup.shutdown = lambda reason, code: shut.append((reason, code))
    sup._out_of_fuel_dialog_show_fn = _slow

    # Call real quit — uses patched show_out_of_fuel_dialog
    bw.Supervisor._quit_after_out_of_fuel(sup, "fuel-exhausted:opencode-free")
    gate.set()
    assert removed and removed[0].get("nick") == "redqueen-13608"
    assert shut == [("fuel-exhausted", bw.EXIT_OUT_OF_FUEL)]


def test_fr9016_fuel_hold_skipped_after_quit_started():
    """No progress-heartbeat: fuel-hold after quit decision."""
    called = {"n": 0}
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.log = lambda *_a, **_k: None
    sup._out_of_fuel_quit_started = True
    sup._shutting = False
    sup.stop = threading.Event()
    bored = SimpleNamespace(
        heartbeat_snapshot=lambda: SimpleNamespace(
            out_of_fuel=True,
            ack_open=False,
            ack_job_key=None,
            turn_gen=0,
        )
    )
    sup.bored = bored
    sup._progress_prev = {}
    sup._progress_phase = ""
    sup._progress_hb_epoch = 0
    sup.clock = lambda: 100.0
    sup.proc = None
    sup.kind = "opencode"
    sup.run_dir = Path(".")
    sup._post_fuel_hold_heartbeat = lambda **_k: called.__setitem__("n", called["n"] + 1)
    bw.Supervisor._maybe_progress_heartbeat(sup)
    assert called["n"] == 0


def test_fr9016_restart_during_fuel_quit_shuts_down_not_respawn():
    """CLI 0xffffffff during fuel-quit must shutdown, not leave a fuel-hold zombie."""
    logs: list[str] = []
    shut: list[tuple[str, int]] = []
    started: list[str] = []

    bored = SimpleNamespace(out_of_fuel=True, _ack_open=False, _ack_job_key=None)
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.log = logs.append
    sup.bored = bored
    sup._out_of_fuel_quit_started = True
    sup._shutting = False
    sup.proc = SimpleNamespace(pid=4120, poll=lambda: 4294967295)
    sup._lock = threading.RLock()
    sup.restarts = []
    sup.restart_window_s = 600.0
    sup.restart_max = 3
    sup.backoff = [0.0]
    sup.clock = lambda: 1.0
    sup._expected_exit = set()
    sup.ask_user_watch = SimpleNamespace(clear=lambda: None)
    sup.relay = SimpleNamespace(
        set_target=lambda *_a, **_k: None, last_unacked="", hold=lambda *_a: None
    )
    sup.kill = lambda *_a, **_k: None
    sup.start_agent = lambda **_k: started.append("start") or True
    sup.shutdown = lambda reason, code: shut.append((reason, code))
    sup._clear_watchdogs_for_out_of_fuel = lambda: None
    sup._record_exit = lambda *_a, **_k: None

    bw.Supervisor.restart_agent(sup, "agent-cli-nonzero-exit")
    assert started == []
    assert shut and shut[0] == ("fuel-exhausted", bw.EXIT_OUT_OF_FUEL)


def test_fr9016_wait_exit_nonzero_during_fuel_hold_closes(monkeypatch):
    """_wait_exit during out-of-fuel closes the seat (no recycle hang)."""
    logs: list[str] = []
    shut: list[tuple[str, int]] = []

    proc = SimpleNamespace(
        pid=13608, wait=lambda: 4294967295, stderr_tail=lambda: "OSError: [Errno 22]"
    )
    bored = SimpleNamespace(out_of_fuel=True, _ack_open=False, _ack_job_key=None)
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.log = logs.append
    sup.bored = bored
    sup._out_of_fuel_quit_started = True
    sup._shutting = False
    sup.proc = proc
    sup._lock = threading.RLock()
    sup._expected_exit = set()
    sup._agent_started_at = 0.0
    sup.clock = lambda: 100.0
    sup.startup_grace_s = 30.0
    sup.kind = "opencode"
    sup.machine = "redqueen"
    sup.nick = "redqueen-13608"
    sup.last_exit = None
    sup.sessions = []
    sup._agent_parent_pid = 0
    sup._agent_parent_image = ""
    sup._agent_parent_cmd = ""
    sup._record_exit = lambda *_a, **_k: True
    sup._reconcile_wait_exit_with_shutdown = lambda *_a, **_k: False
    sup._persist_last_exit = lambda: None
    monkeypatch.setattr(bw, "report_agent_cli_nonzero_exit", lambda **_k: None)
    monkeypatch.setattr(bw, "parent_of", lambda *_a, **_k: 0)
    monkeypatch.setattr(bw, "describe_process", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(
        bw, "format_external_kill_log", lambda **_k: "terminated-by-external-kill"
    )
    monkeypatch.setattr(bw, "normalize_agent_exit_code", lambda c: int(c) & 0xFFFFFFFF)
    monkeypatch.setattr(bw, "format_agent_exit_code_label", lambda c: "0xffffffff")
    monkeypatch.setattr(bw, "CONSOLE_CLOSE_EXIT", 0xC000013A)

    def _shutdown(reason: str, code: int) -> None:
        shut.append((reason, code))

    # Real restart_agent on this stub → should shutdown via fuel-quit gate
    sup.shutdown = _shutdown
    sup._clear_watchdogs_for_out_of_fuel = lambda: None
    sup.restarts = []
    sup.restart_window_s = 600.0
    sup.restart_max = 3
    sup.backoff = [0.0]
    sup._expected_exit = set()
    sup.ask_user_watch = SimpleNamespace(clear=lambda: None)
    sup.relay = SimpleNamespace(
        set_target=lambda *_a, **_k: None, last_unacked="", hold=lambda *_a: None
    )
    sup.kill = lambda *_a, **_k: None
    sup.start_agent = lambda **_k: False
    sup._record_exit = lambda *_a, **_k: True

    bw.Supervisor._wait_exit(sup, proc)
    assert shut and shut[0] == ("fuel-exhausted", bw.EXIT_OUT_OF_FUEL)
