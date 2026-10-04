"""FR #1643: log external kill / parent on unexpected agent exit; defer bin delete while seat holds hashed exe."""
from __future__ import annotations

import bob_worker as bw


def test_fr1643_describe_parent_helpers_exist():
    assert hasattr(bw, "describe_process")
    assert hasattr(bw, "format_external_kill_log")
    line = bw.format_external_kill_log(
        agent_pid=42,
        agent_code=1,
        parent_pid=7,
        parent_image="bob-tray.exe",
        parent_cmd="C:\\ai\\bob\\tools\\bob-tray.exe",
    )
    assert "terminated-by-external-kill" in line or "external kill" in line.lower()
    assert "pid=42" in line
    assert "parent_pid=7" in line
    assert "bob-tray.exe" in line


def test_fr1643_wait_exit_logs_parent_on_unexpected(monkeypatch, tmp_path):
    logs: list[str] = []

    class FakeProc:
        pid = 4242

        def wait(self):
            return 1

        def poll(self):
            return 1

    class FakeRelay:
        last_unacked = "FROM Jeeves #m FR x"
        on_inject = None

        def close(self):
            pass

        def set_target(self, *a, **k):
            pass

    class FakeIrc:
        shop = "#m"
        alive = True
        on_nak = None
        on_lost = None

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "killer.exe", "killer.exe --force"))
    monkeypatch.setattr(bw, "parent_of", lambda pid: 99)
    sup = bw.Supervisor(
        kind="grok", exe="x", cwd=str(tmp_path), machine="m", nick="m-1",
        run_dir=tmp_path, irc=FakeIrc(), relay=FakeRelay(), log=logs.append,
        bored=None, startup_grace_s=0.0,
    )
    sup.proc = FakeProc()
    sup._agent_started_at = bw.time.monotonic() - 120.0
    sup._wait_exit(FakeProc())
    joined = "\n".join(logs)
    assert "external" in joined.lower() or "parent" in joined.lower()
    assert "4242" in joined or "agent:" in joined


def test_fr1643_ps1_defers_locked_bin_delete():
    from pathlib import Path
    import re

    tray = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"
    text = tray.read_text(encoding="utf-8")
    fn = text[text.index("function Start-BobTrayWorkerExe") : text.index("\nfunction ", text.index("function Start-BobTrayWorkerExe") + 10)]
    assert "FR #1643" in fn or "in use" in fn.lower() or "defer" in fn.lower()
    assert "Remove-Item" in fn


def test_fr1643_csharp_defers_locked_bin_delete():
    from pathlib import Path

    cs = Path(__file__).resolve().parents[1] / "tray" / "dialogs" / "BobTray.cs"
    text = cs.read_text(encoding="utf-8")
    assert "FR #1643" in text or "WorkerBinInUse" in text or "IsWorkerExeInUse" in text
    assert "File.Delete" in text


def test_fr1643_spawn_cached_parent_used_when_live_lookup_empty(monkeypatch, tmp_path):
    """MRB #1658 hostile: after wait(), parent_of often returns 0; spawn-time cache must still log."""
    logs: list[str] = []

    class FakeProc:
        pid = 5151

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
        shop = "#m"
        alive = True
        on_nak = None
        on_lost = None

        def close(self, *a, **k):
            pass

        def say(self, *a, **k):
            return True

    # Live lookup empty (post-wait); spawn cache must supply parent.
    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (pid, "", ""))
    sup = bw.Supervisor(
        kind="grok", exe="x", cwd=str(tmp_path), machine="m", nick="m-1",
        run_dir=tmp_path, irc=FakeIrc(), relay=FakeRelay(), log=logs.append,
        bored=None, startup_grace_s=0.0,
    )
    sup.proc = FakeProc()
    sup._agent_started_at = bw.time.monotonic() - 120.0
    sup._agent_parent_pid = 77
    sup._agent_parent_image = "bob-worker.exe"
    sup._agent_parent_cmd = "bob-worker.exe --mode agent"
    sup._wait_exit(FakeProc())
    joined = "\n".join(logs)
    assert "terminated-by-external-kill" in joined
    assert "parent_pid=77" in joined
    assert "bob-worker.exe" in joined
