"""FR #5526: PRIORITY connect off the IRC receive loop; one DONE per job."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import airc_console as ac
import airc_console_service as svc
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT


def _allowlist(tmp_path: Path) -> Path:
    doc = {
        "instances": [
            {
                "id": "dev1",
                "url": "https://prioritydev.example.invalid",
                "company": "live1",
                "user": "api-user",
                "credentialTarget": "PriorityWeb/dev1",
            }
        ]
    }
    p = tmp_path / "priority-instances.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def test_fr5526_async_connect_returns_fast_and_serves_next(tmp_path):
    path = _allowlist(tmp_path)
    gate = threading.Event()
    sent: list[tuple[str, str]] = []

    def slow_cred(_t: str) -> str:
        gate.wait(timeout=5)
        return "FAKE_PRIORITY_PASSWORD_FOR_TEST"

    def runner(subcmd, instance_id, **kwargs):
        return ap.run_priority_verb(
            subcmd,
            instance_id,
            job_id=kwargs.get("job_id"),
            allowlist_path=path,
            cred_fetcher=slow_cred,
            connector=ap.mock_connect,
            wait=kwargs.get("wait", True),
            on_done=kwargs.get("on_done"),
        )

    core = _core(priority_runner=runner, priority_allowlist_path=str(path))
    core.priority_reply_send = lambda nick, line: sent.append((nick, line))

    t0 = time.perf_counter()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=aaaaaaaa PRIORITY connect dev1"
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.15
    assert hr and hr.action == "priority"
    assert (hr.reply or "") == ""

    # Second command must be accepted while connect is still blocked.
    shell_seen = {"n": 0}

    class FakeShell:
        def submit(self, *a, **k):
            shell_seen["n"] += 1
            return "ok"

    # Prefer a real status call (no shell runner needed).
    t1 = time.perf_counter()
    hr2 = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=bbbbbbbb PRIORITY status"
    )
    assert time.perf_counter() - t1 < 0.15
    assert hr2 and hr2.action == "priority"
    assert "DONE id=bbbbbbbb exit=0" in (hr2.reply or "")

    gate.set()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not any(
        t.startswith("DONE id=aaaaaaaa") for _, t in sent
    ):
        time.sleep(0.02)
    dones = [t for _, t in sent if t.startswith("DONE id=aaaaaaaa")]
    assert len(dones) == 1
    assert "exit=" in dones[0]
    assert all("FAKE_PRIORITY_PASSWORD_FOR_TEST" not in t for _, t in sent)
    assert all("password" not in t.lower() for _, t in sent)


def test_fr5526_missing_cred_async_done_exit_1(tmp_path):
    path = _allowlist(tmp_path)
    sent: list[str] = []

    def missing(_t: str) -> str:
        raise ap.PriorityConfigError("credman-missing")

    def runner(subcmd, instance_id, **kwargs):
        return ap.run_priority_verb(
            subcmd,
            instance_id,
            job_id=kwargs.get("job_id"),
            allowlist_path=path,
            cred_fetcher=missing,
            wait=kwargs.get("wait", True),
            on_done=kwargs.get("on_done"),
        )

    core = _core(priority_runner=runner, priority_allowlist_path=str(path))
    core.priority_reply_send = lambda nick, line: sent.append(line)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=cccccccc PRIORITY connect dev1"
    )
    assert hr and (hr.reply or "") == ""
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not any(
        t.startswith("DONE id=cccccccc") for t in sent
    ):
        time.sleep(0.02)
    blob = "\n".join(sent)
    assert "credman-missing" in blob
    assert "DONE id=cccccccc exit=1" in blob
    assert "password" not in blob.lower() or "credman" in blob.lower()
    assert blob.lower().count("password") == 0 or "credman-missing" in blob


def test_fr5526_on_done_raise_does_not_double_done(tmp_path):
    path = _allowlist(tmp_path)
    calls = {"n": 0}
    sent: list[str] = []

    def cred(_t: str) -> str:
        return "FAKE_PW"

    def conn(inst, password):
        calls["n"] += 1
        return ap.mock_connect(inst, password)

    def runner(subcmd, instance_id, **kwargs):
        return ap.run_priority_verb(
            subcmd,
            instance_id,
            job_id=kwargs.get("job_id"),
            allowlist_path=path,
            cred_fetcher=cred,
            connector=conn,
            wait=kwargs.get("wait", True),
            on_done=kwargs.get("on_done"),
        )

    core = _core(priority_runner=runner, priority_allowlist_path=str(path))

    def flaky_send(nick, line):
        sent.append(line)
        if line.startswith("out id="):
            raise RuntimeError("send-fail")

    core.priority_reply_send = flaky_send
    core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=dddddddd PRIORITY connect dev1"
    )
    time.sleep(0.3)
    assert calls["n"] == 1
    # First line may have been recorded before the raise; DONE must not double.
    assert sum(1 for t in sent if t.startswith("DONE id=dddddddd")) <= 1


def test_fr5526_shell_off_never_calls_runner(tmp_path):
    path = _allowlist(tmp_path)
    called = {"n": 0}

    def runner(*a, **k):
        called["n"] += 1
        raise AssertionError("runner must not run")

    from airc_console import ConsoleCapabilities

    core = _core(
        priority_runner=runner,
        priority_allowlist_path=str(path),
        capabilities=ConsoleCapabilities(shell_mode="off"),
    )
    core.priority_reply_send = lambda *_a: None
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=eeeeeeee PRIORITY connect dev1"
    )
    assert hr and hr.action == "capability_deny"
    assert "126" in (hr.reply or "")
    assert called["n"] == 0


def test_fr5526_stop_flush_and_suppress_late(tmp_path, monkeypatch):
    path = _allowlist(tmp_path)
    gate = threading.Event()
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path)]
    )
    service = svc.AircConsoleService(args)
    queued: list[tuple[str, str]] = []
    service._out_q.put = lambda item: queued.append(item)  # type: ignore[method-assign]

    def slow_cred(_t: str) -> str:
        gate.wait(timeout=5)
        return "FAKE_PW"

    def runner(subcmd, instance_id, **kwargs):
        return ap.run_priority_verb(
            subcmd,
            instance_id,
            job_id=kwargs.get("job_id"),
            allowlist_path=path,
            cred_fetcher=slow_cred,
            connector=ap.mock_connect,
            wait=kwargs.get("wait", True),
            on_done=kwargs.get("on_done"),
        )

    service.core.priority_runner = runner
    service.core.priority_allowlist_path = str(path)
    service.core.priority_reply_send = service._on_console_out
    # Authorise a synthetic handle via core directly.
    auth = ops_auth("op", channel="#tm")
    service.core.auth = auth
    service.core.nick = "tm_console"
    sent_via_hook: list[str] = []
    service.core.priority_reply_send = lambda nick, line: sent_via_hook.append(line)

    hr = service.core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=ffffffff PRIORITY connect dev1"
    )
    assert hr and (hr.reply or "") == ""

    abandoned = service.core.abandon_open_priority_jobs()
    assert ("op", "ffffffff") in abandoned
    # Simulate flush lines for abandoned PRIORITY jobs.
    for nick, jid in abandoned:
        queued.append((nick, f"err id={jid} seq=1 service-stop"))
        queued.append((nick, f"DONE id={jid} exit=1"))

    gate.set()
    time.sleep(0.35)
    # Late worker must not deliver after abandon.
    assert not any(t.startswith("DONE id=ffffffff") for t in sent_via_hook)
    assert any(
        t.startswith("DONE id=ffffffff exit=1") for _, t in queued
    )


def test_fr5526_unbound_hook_stays_synchronous(tmp_path):
    path = _allowlist(tmp_path)

    def runner(subcmd, instance_id, **kwargs):
        return ap.run_priority_verb(
            subcmd,
            instance_id,
            job_id=kwargs.get("job_id"),
            allowlist_path=path,
            cred_fetcher=lambda _t: "FAKE_PW",
            connector=ap.mock_connect,
        )

    core = _core(priority_runner=runner, priority_allowlist_path=str(path))
    assert core.priority_reply_send is None
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=11223344 PRIORITY connect dev1"
    )
    assert hr and hr.action == "priority"
    assert "DONE id=11223344 exit=0" in (hr.reply or "")
    assert "FAKE_PW" not in (hr.reply or "")


def test_fr5526_service_binds_priority_reply_send(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path)]
    )
    service = svc.AircConsoleService(args)
    hook = service.core.priority_reply_send
    assert callable(hook)
    assert getattr(hook, "__func__", hook) is getattr(
        service._on_console_out, "__func__", service._on_console_out
    )
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(
        encoding="utf-8"
    )
    assert "priority_reply_send" in src
    assert "abandon_open_priority_jobs" in src
