"""FR #6158 / FR-OC-INJECT: OpenCode keys default, path log, submit probe, GIVEUP."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import bob_worker as bw


ASSIGN = (
    "FROM Jeeves #redqueen redqueen-1: FR SimonBarnett/bobiverse#6158 "
    "https://github.com/SimonBarnett/bobiverse/issues/6158"
)
GIVEUP = "GIVEUP FR SimonBarnett/bobiverse#6158 submit-verify failed"


class _Proc:
    def __init__(self, pid: int = 5158):
        self.pid = pid

    def poll(self):
        return None


class _Thread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self):
        return None


def test_fr6158_keys_default_for_opencode_when_unset(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    logs: list[str] = []
    assert bw.apply_cursor_inject_keys_default("opencode", log=logs.append) is True
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    assert any("opencode" in line.lower() and "batched keys" in line for line in logs)


def test_fr6158_keys_default_explicit_paste_wins(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "1")
    assert bw.apply_cursor_inject_keys_default("opencode") is False
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "1"


def test_fr6158_start_agent_sets_keys_for_opencode(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    monkeypatch.setenv("BOB_WORKER_OPENCODE_TURN_WATCH", "0")
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "test-model")
    monkeypatch.setattr(bw.threading, "Thread", _Thread)
    # FR #6668 / #6240: start_agent probes gh auth before spawn; CI seats often lack gh login.
    monkeypatch.setattr(bw, "probe_gh_auth", lambda *_a, **_k: (False, ""))
    logs: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: 0.0, persist_dir=tmp_path)

    def spawn(spec, env):
        return _Proc()

    # Fake exe path so build_launch succeeds
    exe = tmp_path / "opencode.exe"
    exe.write_text("", encoding="utf-8")
    sup = bw.Supervisor(
        kind="opencode",
        exe=str(exe),
        cwd=str(tmp_path),
        machine="redqueen",
        nick="redqueen-17556",
        run_dir=tmp_path,
        irc=None,
        relay=relay,
        log=logs.append,
        spawn=spawn,
        startup_grace_s=0,
        clock=lambda: 0.0,
    )
    assert sup.start_agent() is True
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    assert any("batched keys" in line for line in logs)


def test_fr6158_inject_console_path_log_includes_kind():
    import inspect
    src = inspect.getsource(bw.inject_console)
    assert "kind" in src
    assert "kind=" in src
    # Signature accepts kind=
    assert "kind" in bw.inject_console.__code__.co_varnames


def test_fr6158_probe_opencode_turns_after_since(tmp_path: Path):
    turns = tmp_path / "opencode-turns.jsonl"
    # Old marker before baseline
    with turns.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "turn_started", "ts": "2020-01-01T00:00:00Z", "turn_number": 1}) + "\n")
    t0 = time.time()
    assert bw.probe_opencode_turns_submit(turns, since_wall=t0) is False
    with turns.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "turn_started",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0 + 5)),
                    "turn_number": 2,
                }
            )
            + "\n"
        )
    assert bw.probe_opencode_turns_submit(turns, since_wall=t0) is True


def test_fr6158_make_submit_probe_opencode(tmp_path: Path):
    turns = tmp_path / "opencode-turns.jsonl"
    turns.write_text("", encoding="utf-8")
    t0 = time.time() - 1.0
    probe = bw.make_submit_probe("opencode", run_dir=tmp_path, since_wall=t0, text=ASSIGN)
    assert probe is not None
    assert probe() is False
    with turns.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "turn_started",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 1)),
                    "turn_number": 3,
                }
            )
            + "\n"
        )
    assert probe() is True
    assert bw.make_submit_probe("opencode", run_dir=None) is None


def test_fr6158_recovery_giveup_ignores_receipt_ack():
    pasted: list[str] = []

    def reinject(line, cb):
        pasted.append(line)
        cb()
        return True

    state = {"outbox": [], "local": [], "input": []}
    rec = bw.InjectRecovery(
        reinject=reinject,
        write_outbox=lambda text: state["outbox"].append(text) or True,
        clear_local=lambda line: state["local"].append(line),
        is_acked=lambda line: True,
        log=lambda m: None,
        giveup_on_fail=True,
        block_on_receipt_ack=False,
        turn_running=lambda: False,
        clear_input=lambda: state["input"].append("cleared"),
    )
    rec.on_failed(ASSIGN, attempt=1)
    assert state["outbox"] == [GIVEUP]
    assert pasted == [ASSIGN]


def test_fr6158_recovery_skips_reinject_when_turn_running():
    pasted: list[str] = []
    rec = bw.InjectRecovery(
        reinject=lambda line, cb: pasted.append(line) or True,
        write_outbox=lambda text: True,
        clear_local=lambda line: None,
        is_acked=lambda line: True,
        log=lambda m: None,
        giveup_on_fail=True,
        block_on_receipt_ack=False,
        turn_running=lambda: True,
        clear_input=lambda: None,
    )
    assert rec.on_failed(ASSIGN, attempt=1) == "running"
    assert pasted == []


def test_fr6158_supervisor_recovery_treats_opencode_like_cursor(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "test-model")
    monkeypatch.setattr(bw.threading, "Thread", _Thread)
    logs: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: 0.0, persist_dir=tmp_path)
    exe = tmp_path / "opencode.exe"
    exe.write_text("", encoding="utf-8")
    sup = bw.Supervisor(
        kind="opencode",
        exe=str(exe),
        cwd=str(tmp_path),
        machine="redqueen",
        nick="redqueen-17556",
        run_dir=tmp_path,
        irc=None,
        relay=relay,
        log=logs.append,
        spawn=lambda spec, env: _Proc(),
        startup_grace_s=0,
        clock=lambda: 0.0,
    )
    rec = sup._inject_recovery()
    assert rec.giveup_on_fail is True
    assert rec.block_on_receipt_ack is False
