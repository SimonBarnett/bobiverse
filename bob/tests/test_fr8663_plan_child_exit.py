"""FR #8663: plan child non-zero exit is not success."""
import json

import bob_worker as bw


def _args(tmp_path):
    (tmp_path / "plan").mkdir(exist_ok=True)
    return type("A", (), {"install_root": str(tmp_path), "machine_id": "testbox", "agent": ""})()


def _patch(monkeypatch, code, stderr=""):
    class P:
        pid = 4242

        def wait(self, timeout=None):
            return code

        def stderr_tail(self):
            return stderr

    monkeypatch.setattr(bw, "default_spawn", lambda spec, env: P())
    monkeypatch.setattr(bw, "read_fuel", lambda root: bw.Fuel(30, 30, 30, "available"))
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: r"C:\c\agent.cmd")
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: r"C:\g\agent.exe")
    monkeypatch.setattr(bw, "install_ctrl_handler", lambda fn: True)


def test_plan_nonzero_child_is_not_success(tmp_path, monkeypatch):
    _patch(monkeypatch, 4294967295, stderr="grok died mid-stream")
    lines = []
    rc = bw.run_plan(_args(tmp_path), lines.append)
    assert rc == bw.EXIT_PLAN_CHILD
    text = "\n".join(lines)
    assert "plan: agent ended code=4294967295" in text
    assert "plan: FAILED child exit is not success" in text
    assert "plan: child stderr: grok died mid-stream" in text
    assert "no session_end" in text


def test_plan_repeated_hard_exit_logs_heal_tip(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    _patch(monkeypatch, -1, stderr="")
    lines = []
    assert bw.run_plan(_args(tmp_path), lines.append) == bw.EXIT_PLAN_CHILD
    assert bw.run_plan(_args(tmp_path), lines.append) == bw.EXIT_PLAN_CHILD
    assert any("heal tip" in line for line in lines)
    stamp = tmp_path / "lad" / "Bobiverse" / "worker" / "plan-hard-exit.json"
    assert json.loads(stamp.read_text(encoding="utf-8"))
