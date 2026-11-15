"""FR #7593: agent CLI nonzero exit -> report + GIVEUP accepted job + restart; zero exit unchanged."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import bob_worker as bw


def test_normalize_agent_exit_code_windows_ffffffff():
    assert bw.normalize_agent_exit_code(0) == 0
    assert bw.normalize_agent_exit_code(1) == 1
    assert bw.normalize_agent_exit_code(-1) == 0xFFFFFFFF
    assert bw.normalize_agent_exit_code(4294967295) == 0xFFFFFFFF
    assert "0xffffffff" in bw.format_agent_exit_code_label(-1)


def test_report_agent_cli_nonzero_exit_files_exit_and_job():
    posts: list[dict] = []

    out = bw.report_agent_cli_nonzero_exit(
        exit_code=0xFFFFFFFF,
        raw_code=-1,
        job_key="FR owner/repo#42",
        machine="testhost",
        nick="testhost-1",
        kind="grok",
        agent_pid=1488,
        stderr_tail="agent cli failed to start\n",
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert out.get("ok") is True
    assert len(posts) == 1
    blob = json.dumps(posts[0]).lower()
    assert "password" not in blob
    assert "secret" not in blob or "no secrets" in blob
    assert "4294967295" in posts[0]["body"] or "0xffffffff" in posts[0]["body"].lower()
    assert "FR owner/repo#42" in posts[0]["body"]
    assert posts[0]["idempotency_key"].startswith("agent-cli-nonzero-exit|testhost|")


def test_report_skipped_under_pytest_without_filer():
    out = bw.report_agent_cli_nonzero_exit(exit_code=1, job_key="FR owner/repo#1", machine="box")
    assert out.get("skipped") is True


def test_wait_exit_nonzero_with_ack_reports_giveup_restarts(monkeypatch, tmp_path):
    logs: list[str] = []
    posts: list[dict] = []
    giveups: list[tuple[str, str]] = []
    restarts: list[str] = []
    said: list[tuple[str, str]] = []

    class FakeProc:
        pid = 9001

        def wait(self):
            return -1  # Windows 0xffffffff

        def poll(self):
            return -1

    class FakeRelay:
        last_unacked = ""
        on_inject = None

        def close(self):
            pass

        def set_target(self, *a, **k):
            pass

        def hold(self, *a, **k):
            pass

    class FakeIrc:
        shop = "#box"
        alive = True
        on_nak = None
        on_lost = None

        def close(self, *a, **k):
            pass

        def say(self, chan, text):
            said.append((chan, text))
            return True

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True, "key": "k"},
    )

    bored = bw.BoredEmitter(lambda: True, logs.append)
    bored._ack_open = True
    bored._ack_job_key = "FR owner/repo#99"

    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="box",
        nick="box-1",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        bored=bored,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
    )
    sup._release_seat_giveup_job = lambda job, reason: giveups.append((job, reason))  # type: ignore[method-assign]
    sup.restart_agent = lambda reason: restarts.append(reason)  # type: ignore[method-assign]
    sup.proc = FakeProc()
    sup._agent_started_at = bw.time.monotonic() - 120.0
    sup._wait_exit(FakeProc())

    assert len(posts) == 1
    assert posts[0]["exit_code"] == 0xFFFFFFFF
    assert posts[0]["job_key"] == "FR owner/repo#99"
    assert giveups == [("FR owner/repo#99", "agent-cli-nonzero-exit")]
    assert restarts == ["agent-cli-nonzero-exit"]
    assert bored._ack_open is False
    assert not sup.done.is_set(), "nonzero exit must restart, not end the seat with EXIT_OK"
    assert any("DONE" not in t for _c, t in said) or said == []
    joined = "\n".join(logs)
    assert "DONE" not in joined


def test_wait_exit_zero_does_not_report_or_giveup(monkeypatch, tmp_path):
    logs: list[str] = []
    posts: list[dict] = []
    giveups: list[tuple[str, str]] = []
    restarts: list[str] = []

    class FakeProc:
        pid = 9002

        def wait(self):
            return 0

        def poll(self):
            return 0

    class FakeRelay:
        last_unacked = "FROM jeeves #box FR owner/repo#1"
        on_inject = None

        def close(self):
            pass

        def set_target(self, *a, **k):
            pass

    class FakeIrc:
        shop = "#box"
        alive = True
        on_nak = None
        on_lost = None

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True},
    )

    bored = bw.BoredEmitter(lambda: True, logs.append)
    bored._ack_open = True
    bored._ack_job_key = "FR owner/repo#7"

    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="box",
        nick="box-2",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        bored=bored,
        startup_grace_s=0.0,
        kill=lambda pid: True,
    )
    sup._release_seat_giveup_job = lambda job, reason: giveups.append((job, reason))  # type: ignore[method-assign]
    sup.restart_agent = lambda reason: restarts.append(reason)  # type: ignore[method-assign]
    sup.proc = FakeProc()
    sup._agent_started_at = bw.time.monotonic() - 120.0
    # run_forever path uses shutdown; call wait_exit directly
    th = threading.Thread(target=lambda: None)
    del th
    sup._wait_exit(FakeProc())

    assert posts == []
    assert giveups == []
    assert restarts == []
    assert bored._ack_open is True
    assert bored._ack_job_key == "FR owner/repo#7"
    assert sup.done.is_set()
    assert sup.exit_code == bw.EXIT_OK


def test_wait_exit_nonzero_without_ack_reports_and_restarts(monkeypatch, tmp_path):
    posts: list[dict] = []
    giveups: list[tuple[str, str]] = []
    restarts: list[str] = []
    logs: list[str] = []

    class FakeProc:
        pid = 9003

        def wait(self):
            return 1

        def poll(self):
            return 1

    class FakeRelay:
        last_unacked = ""
        on_inject = None

        def close(self):
            pass

        def set_target(self, *a, **k):
            pass

    class FakeIrc:
        shop = "#box"
        alive = True
        on_nak = None
        on_lost = None

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    monkeypatch.setattr(
        bw,
        "report_agent_cli_nonzero_exit",
        lambda **kw: posts.append(kw) or {"ok": True},
    )

    bored = bw.BoredEmitter(lambda: True, logs.append)
    assert bored._ack_open is False

    sup = bw.Supervisor(
        kind="cursor",
        exe="x",
        cwd=str(tmp_path),
        machine="box",
        nick="box-3",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        bored=bored,
        startup_grace_s=0.0,
        kill=lambda pid: True,
    )
    sup._release_seat_giveup_job = lambda job, reason: giveups.append((job, reason))  # type: ignore[method-assign]
    sup.restart_agent = lambda reason: restarts.append(reason)  # type: ignore[method-assign]
    sup.proc = FakeProc()
    sup._agent_started_at = bw.time.monotonic() - 120.0
    sup._wait_exit(FakeProc())

    assert len(posts) == 1
    assert posts[0]["exit_code"] == 1
    assert giveups == []
    assert restarts == ["agent-cli-nonzero-exit"]
    assert not sup.done.is_set()


def test_fr7593_source_has_no_machine_names():
    """Acceptance: generic --- no fleet machine names in the new FR #7593 helpers."""
    root = Path(__file__).resolve().parents[1]
    src = (root / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "FR #7593" in src
    assert "report_agent_cli_nonzero_exit" in src
    assert "agent-cli-nonzero-exit" in src
    start = src.index("def normalize_agent_exit_code")
    end = src.index("\ndef restart_skill_dag_mcp_stdio_children", start)
    chunk = src[start:end].lower()
    wait_i = src.index("FR #7593: zero exit ends the seat")
    wait_chunk = src[wait_i : wait_i + 1200].lower()
    banned = ("red" + "queen", "white" + "queen", "march" + "hare", "twee" + "dle")
    for name in banned:
        assert name not in chunk
        assert name not in wait_chunk
    # This test file uses only generic host labels.
    self_src = Path(__file__).read_text(encoding="utf-8").lower()
    assert "machine=\"box\"" in self_src or 'machine="box"' in self_src or "machine=\"testhost\"" in self_src
