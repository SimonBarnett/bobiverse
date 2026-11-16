"""FR #7671: nonzero agent exit report quotes redacted stderr and dedupes on it."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import bob_worker as bw
import pytest


def test_fr7671_fake_cli_stderr_is_in_the_report():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stderr.write('failed to start the acp-agent-worker runtime\\n'); raise SystemExit(1)"],
        stderr=subprocess.PIPE,
    )
    ring, thread = bw.start_agent_stderr_capture(proc.stderr)
    assert proc.wait(timeout=20) == 1
    thread.join(timeout=2)
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#1",
        machine="seat",
        stderr_tail=ring.tail_text(),
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "acp-agent-worker runtime" in posts[0]["body"]


def test_fr7671_secret_in_stderr_is_redacted():
    raw = "blocked password=EXAMPLEVALUE then continued\n"
    evidence = bw.agent_stderr_evidence(raw)
    assert "EXAMPLEVALUE" not in evidence
    assert "<redacted>" in evidence
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        job_key="FR owner/repo#9",
        machine="seat",
        stderr_tail=raw,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    blob = json.dumps(posts[0])
    assert "EXAMPLEVALUE" not in blob


def test_fr7671_identical_crashes_share_one_dedupe_key():
    line = "failed to start the acp-agent-worker runtime: blocking pool pre-warm stalled"
    keys = []
    for job in ("FR owner/repo#1", "FR owner/repo#2"):
        bw.report_agent_cli_nonzero_exit(
            exit_code=1,
            job_key=job,
            machine="redqueen",
            stderr_tail=line + "\n",
            filer_post=lambda p: keys.append(p["idempotency_key"]) or {"ok": True},
        )
    assert keys[0] == keys[1]
    assert "repo#1" not in keys[0]
    assert "acp-agent-worker" in keys[0]


def test_fr7671_mrb_empty_stderr_dedupe_and_trim():
    """Hostile: empty stderr uses none key; evidence caps at 500 chars."""
    keys = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=7,
        job_key="FR owner/repo#3",
        machine="box",
        stderr_tail="",
        filer_post=lambda p: keys.append(p["idempotency_key"]) or {"ok": True},
    )
    assert "|none" in keys[0]
    long = ("noise line\n" * 3) + ("Y" * 600)
    ev = bw.agent_stderr_evidence(long)
    assert len(ev) <= 500
    assert "EXAMPLESECRET" not in bw.agent_stderr_evidence("token password=EXAMPLESECRET end")


@pytest.mark.parametrize("kind", ["grok", "cursor", "opencode"])
@pytest.mark.parametrize("mode", ["agent", "plan", "monitor", "maintenance"])
def test_default_spawn_preserves_grok_console_handles(monkeypatch, tmp_path, kind, mode):
    """Grok needs all three console handles; other agents keep stderr capture."""
    seen = {}

    class FakePopen:
        def __init__(self, *a, **kw):
            seen.update(kw)
            self.pid = 4242
            self.stderr = kw.get("stderr")
            self.stdout = kw.get("stdout")

    monkeypatch.setattr(bw.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(bw, "owned_job", lambda: type("J", (), {"assign": lambda self, p: None})())
    spec = bw.build_launch(kind, mode, str(tmp_path), "p", r"C:\g\agent.exe", tmp_path, "sid")
    handle = bw.default_spawn(spec, {})
    assert seen.get("creationflags", 0) & getattr(bw, "CREATE_NEW_CONSOLE", 0x10) == 0
    assert seen.get("creationflags", 0) & getattr(bw, "CREATE_NO_WINDOW", 0x08000000) == 0
    assert seen.get("stdin") is None
    assert seen.get("stdout") is (bw.subprocess.PIPE if kind == "opencode" else None)
    assert seen.get("stderr") is (None if kind == "grok" else bw.subprocess.PIPE)
    if kind == "grok":
        assert "--no-alt-screen" in spec.argv
        assert handle.stderr_tail() == ""
    assert isinstance(handle, bw.ProcHandle)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console handles and buffer")
def test_grok_console_child_renders_after_first_prompt(tmp_path):
    """Exercise the worker spawn in an isolated console, without Grok auth/network."""
    ready = tmp_path / "ready"
    result = tmp_path / "result.json"
    host = tmp_path / "host.py"
    child = textwrap.dedent(f"""
        import ctypes, sys
        from ctypes import wintypes as W
        from pathlib import Path
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetStdHandle.argtypes = [W.DWORD]
        k.GetStdHandle.restype = W.HANDLE
        k.GetConsoleMode.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        for stream in (-10, -11, -12):
            mode = W.DWORD()
            assert k.GetConsoleMode(k.GetStdHandle(stream), ctypes.byref(mode))
        Path({str(ready)!r}).touch()
        assert sys.stdin.readline().strip() == "first prompt"
        sys.stderr.write("Tool output: first prompt accepted\\n+----------------+\\n| >              |\\n+----------------+\\n")
        sys.stderr.flush()
    """)
    host.write_text(textwrap.dedent(f"""
        import json, os, sys, time
        from pathlib import Path
        sys.path.insert(0, {str(Path(bw.__file__).parent)!r})
        import bob_worker as bw
        os.environ["BOB_WORKER_INJECT_PASTE"] = "0"
        spec = bw.build_launch("grok", "agent", {str(tmp_path)!r}, "p", sys.executable, Path({str(tmp_path)!r}), "sid")
        spec.argv = [sys.executable, "-c", {child!r}]
        proc = bw.default_spawn(spec, dict(os.environ))
        deadline = time.monotonic() + 10
        while not Path({str(ready)!r}).exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert Path({str(ready)!r}).exists(), "child did not receive console handles"
        assert bw.inject_console(proc.pid, "first prompt")
        code = proc.wait(timeout=10)
        screen = bw.read_console_screen_text(max_lines=100) or ""
        Path({str(result)!r}).write_text(json.dumps({{"code": code, "screen": screen}}), encoding="utf-8")
    """), encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(host)], creationflags=bw.CREATE_NEW_CONSOLE)
    try:
        assert proc.wait(timeout=30) == 0
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["code"] == 0
        assert "Tool output: first prompt accepted" in data["screen"]
        assert bw.grok_console_has_tui_chrome(data["screen"])
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
