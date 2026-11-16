"""Seat diagnostics survive crashes without stealing Grok's console handles."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import bob_worker as bw
import bobcallback
import bobreport
import registered_machines
from crash_report import redact
from seat_session_log import SeatSessionLog, console_startup_state


def supervisor(tmp_path, monkeypatch, kind="grok"):
    monkeypatch.setattr(bw, "read_console_screen_text", lambda **kw: None)
    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    relay = SimpleNamespace(last_unacked="", close=lambda: None, set_target=lambda *a: None)
    sup = bw.Supervisor(
        kind=kind, exe="unused", cwd=str(tmp_path), machine="flamingo",
        nick="flamingo-123", run_dir=tmp_path, irc=None, relay=relay, log=lambda _: None,
        kill=lambda _: True, startup_grace_s=0,
    )
    sup.restart_agent = lambda reason: None
    return sup


def test_nonzero_seat_logs_output_reports_code_and_publishes_last_exit(tmp_path, monkeypatch):
    sup = supervisor(tmp_path, monkeypatch, "opencode")
    posts, digest = [], []
    report = bw.report_agent_cli_nonzero_exit
    monkeypatch.setattr(
        bw, "report_agent_cli_nonzero_exit",
        lambda **kw: report(**kw, filer_post=lambda payload: posts.append(payload)),
    )
    sup.publish_exit_digest = digest.append
    spec = bw.LaunchSpec(
        argv=[sys.executable, "-c",
              "import sys; print('model: final answer', flush=True); "
              "sys.stderr.write('tool: failed to load runtime\\n'); sys.exit(7)"],
        cwd=str(tmp_path), session_id="fake-session", kind="opencode", session_log=sup.session_log,
    )
    sup.proc = bw.default_spawn(spec, dict(bw.os.environ))
    sup._wait_exit(sup.proc)
    text = sup.session_log.path.read_text()
    assert "model: final answer" in text
    assert "tool: failed to load runtime" in text
    assert "exit_code=7" in posts[0]["body"]
    assert "failed to load runtime" in posts[0]["body"]
    assert digest[0]["exit_code"] == 7
    assert digest[0]["reason"] == "agent-cli-nonzero-exit"
    assert json.loads((tmp_path / "last-exit.json").read_text()) == digest[0]


@pytest.mark.parametrize("secret", [
    "api_key=example-value", json.dumps({"password": "two word value"}),
    "Authorization" + ": Bearer " + "example-bearer", "ghp_" + "a" * 30, "sk-" + "b" * 30,
    json.dumps({"output": json.dumps({"password": "two word value"})}),
    json.dumps({"password": 'prefix"one two three four five six'}),
])
def test_secrets_never_reach_log_report_or_digest(tmp_path, monkeypatch, secret):
    sup = supervisor(tmp_path, monkeypatch)
    posts, digest = [], []
    sup.publish_exit_digest = digest.append
    report = bw.report_agent_cli_nonzero_exit
    monkeypatch.setattr(
        bw, "report_agent_cli_nonzero_exit",
        lambda **kw: report(**kw, filer_post=lambda payload: posts.append(payload)),
    )
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps({"type": "tool_call", "output": secret}) + "\n")
    monkeypatch.setattr(sup, "_session_log_paths", lambda: [source])
    sup.proc = SimpleNamespace(pid=1234, wait=lambda: 1, poll=lambda: 1, stderr_tail=lambda: secret)
    sup._wait_exit(sup.proc)
    blob = sup.session_log.path.read_text() + json.dumps(posts) + json.dumps(digest)
    assert secret not in blob
    assert "<redacted" in blob
    for value in ("example-value", "two word value", "one two three four five six", "example-bearer", "a" * 30, "b" * 30):
        assert value not in blob


def test_split_secret_and_oversized_record_are_not_persisted(tmp_path):
    source = tmp_path / "events.jsonl"
    log = SeatSessionLog(tmp_path / "session.log")
    source.write_bytes(b'{"token": "split')
    log.collect([source])
    assert not log.path.exists()
    with source.open("ab") as stream:
        stream.write(b'-value"}\n')
    log.collect([source])
    assert "split-value" not in log.path.read_text()
    with source.open("ab") as stream:
        stream.write(b"token=" + b"x" * 70000)
    log.collect([source])
    with source.open("ab") as stream:
        stream.write(b"suffix\nsafe final output\n")
    log.collect([source], final=True)
    assert "suffix" not in log.path.read_text()
    assert "safe final output" in log.path.read_text()


def test_rotation_caps_every_file_and_preserves_latest_output(tmp_path):
    log = SeatSessionLog(tmp_path / "session.log", max_bytes=1024, backups=2)
    for n in range(100):
        log.write("model", f"output {n} " + "x" * 300)
    files = list(tmp_path.iterdir())
    assert len(files) == 3
    assert all(path.stat().st_size <= 1024 for path in files)
    assert "output 99" in log.path.read_text()


def test_final_snapshot_keeps_last_lines_after_a_large_burst(tmp_path):
    log = SeatSessionLog(tmp_path / "session.log")
    source = tmp_path / "events.jsonl"
    source.write_text("ordinary output\n" * 30000 + "fatal: last output without newline")
    log.collect([source], final=True)
    assert "fatal: last output without newline" in log.path.read_text()


def test_escaped_quotes_are_redacted_by_shared_report_and_digest_filters():
    raw = json.dumps({"password": 'prefix"remaining secret suffix'})
    assert "remaining secret suffix" not in redact(raw)
    assert "remaining secret suffix" not in bobreport.coerce_last_exit({"output": raw})["output"]


def test_standalone_worker_version_without_pythonpath(tmp_path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    worker = Path(bw.__file__).resolve()
    result = subprocess.run(
        [sys.executable, "-B", str(worker), "--version"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == bw.get_source_commit()


def test_grok_uses_own_session_records_and_console_not_redirected_stdio(tmp_path, monkeypatch):
    sup = supervisor(tmp_path, monkeypatch)
    native = tmp_path / "native"
    native.mkdir()
    (native / "events.jsonl").write_text('{"type":"tool_call","name":"read_file"}\n')
    monkeypatch.setattr(bw, "grok_session_dir", lambda *a, **kw: native)
    monkeypatch.setattr(bw, "default_unified_log_path", lambda **kw: native / "unified.jsonl")
    monkeypatch.setattr(bw, "read_console_screen_text", lambda **kw: "assistant: diagnosing crash")
    sup.sessions.append("sid")
    sup._collect_session_log(final=True)
    text = sup.session_log.path.read_text()
    assert "read_file" in text
    assert "assistant: diagnosing crash" in text


def test_stall_records_unknown_exit_code_and_reports_reason_once(tmp_path, monkeypatch):
    sup = supervisor(tmp_path, monkeypatch)
    posts = []
    monkeypatch.setattr(bw, "report_agent_cli_nonzero_exit", lambda **kw: posts.append(kw))
    proc = SimpleNamespace(pid=44, poll=lambda: None)
    sup._record_exit(proc, "no-progress", report=True)
    sup._record_exit(proc, "no-progress", report=True)
    assert sup.last_exit["exit_code"] is None
    assert sup.last_exit["reason"] == "no-progress"
    assert len(posts) == 1
    assert posts[0]["reason"] == "no-progress"
    assert posts[0]["exit_code"] is None


def test_stall_termination_keeps_reason_and_updates_actual_exit_code(tmp_path, monkeypatch):
    sup = supervisor(tmp_path, monkeypatch)
    posts = []
    monkeypatch.setattr(bw, "report_agent_cli_nonzero_exit", lambda **kw: posts.append(kw))
    sup.proc = SimpleNamespace(pid=44, poll=lambda: None, wait=lambda: -9)
    sup.start_agent = lambda **kw: True
    sup.backoff = (0,)
    bw.Supervisor.restart_agent(sup, "no-progress")
    assert posts[0]["reason"] == "no-progress"
    sup._wait_exit(sup.proc)
    assert sup.last_exit["exit_code"] == -9
    assert sup.last_exit["reason"] == "no-progress"
    assert json.loads((tmp_path / "last-exit.json").read_text())["exit_code"] == -9


def test_console_startup_schema_is_available_without_a_console():
    state = console_startup_state()
    assert set(state) >= {
        "host_process", "window_size", "buffer_size", "input_code_page", "output_code_page",
        "TERM", "stdin_mode", "stdout_mode", "stderr_mode", "vt_input", "vt_output", "vt_stderr",
    }


def test_start_logs_console_state_and_initial_prompt(tmp_path, monkeypatch):
    sup = supervisor(tmp_path, monkeypatch)
    state = {key: key for key in console_startup_state()}
    monkeypatch.setattr(bw, "console_startup_state", lambda: state)
    monkeypatch.setattr(sup, "_prompt", lambda: "initial seat instructions")
    spec = bw.LaunchSpec(argv=["unused"], cwd=str(tmp_path), session_id="new-session", kind="grok")
    monkeypatch.setattr(bw, "describe_agent_child_launch", lambda **kw: {"spec": spec, "env": {}})
    sup.spawn = lambda spec, env: SimpleNamespace(pid=99, poll=lambda: None)
    for method in (
        "_start_session_log", "_start_turn_watcher", "_start_fuel_watcher", "_start_prompt_watcher",
        "_start_grok_signin_guard", "_start_grok_blank_tui_guard", "_arm_ready", "_wait_exit",
    ):
        monkeypatch.setattr(sup, method, lambda *a: None)
    assert sup.start_agent()
    text = sup.session_log.path.read_text()
    assert "initial seat instructions" in text
    assert "new-session" in text
    assert all(key in text for key in state)


def test_digest_last_exit_survives_hub_reload_idle_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    registered_machines.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    sent = []
    monkeypatch.setattr(bw, "_http_post_json", lambda url, payload, **kw: sent.append(payload) or True)
    bw.post_digest_seat_kind(
        machine="marchhare", pid=123, nick="marchhare-123", kind="grok",
        last_exit={"reason": "agent-exited", "exit_code": 7, "output": "api_key=example-value"},
    )
    payload = bobcallback.coerce_report_payload(sent[0])
    assert bobcallback.validate_report_payload(tmp_path, payload)[0] == 0
    assert bobreport.apply_callback(tmp_path, payload).ok
    assert bobreport.apply_callback(tmp_path, {
        "op": "worker-work", "machine": "marchhare", "nick": "marchhare-123", "state": "idle",
    }).ok
    doc = bobreport.build_digest_object(tmp_path, "Jeeves")
    last_exit = doc["machines"]["marchhare"]["workers"][0]["last_exit"]
    assert last_exit["exit_code"] == 7
    assert last_exit["reason"] == "agent-exited"
    assert "example-value" not in json.dumps(doc)
    legacy = bobreport.load_digest(tmp_path)["machines"]["marchhare"]["workers"]["123"]
    assert legacy["last_exit"] == last_exit
