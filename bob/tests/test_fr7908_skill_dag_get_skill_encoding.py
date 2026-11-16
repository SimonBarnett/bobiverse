# -*- coding: utf-8 -*-
"""FR #7908: skill-dag get_skill must not close stdio on non-code-page glyphs.

OpenCode launches skill_dag_mcp.py with piped stdio, so ``sys.stdout`` uses the
locale code page (cp1252). ``bobiverse-bob-job-fr/SKILL.md`` contains ``>=`` /
``<->`` glyphs; the old ``ensure_ascii=False`` write raised UnicodeEncodeError
outside the per-call guard, the process exited, and the seat saw
``MCP error -32000: Connection closed``.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import bob_worker as bw
import skill_dag_mcp as mcp

NON_CP1252 = "job >= ready <-> parked\n"


class _Cp1252Stream:
    """Stdout that behaves like a Windows cp1252 pipe: raw non-ASCII raises."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def write(self, text: str) -> int:
        text.encode("cp1252")  # UnicodeEncodeError for e.g. U+2265 / U+2194
        self.parts.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self.parts)


def _tools_call(mid: int, name: str, arguments: dict) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": mid,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


def _skill(root: Path, sid: str, body: str = NON_CP1252) -> Path:
    d = root / sid
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text("---\nname: %s\ndescription: test\n---\n\n%s" % (sid, body), encoding="utf-8")
    return p


def test_fr7908_get_skill_survives_cp1252_stdout(tmp_path: Path):
    root = tmp_path / "skills"
    skill = _skill(root, "bobiverse-bob-job-fr")
    server = mcp.SkillDagServer(roots=[root], max_bytes=65536)
    inf = io.StringIO(
        "\n".join(
            [
                _tools_call(1, "get_skill", {"path": str(skill)}),
                _tools_call(2, "status", {}),
                "",
            ]
        )
    )
    out = _Cp1252Stream()
    mcp.serve_stdio(server, inf, out)

    lines = [json.loads(ln) for ln in out.getvalue().splitlines() if ln.strip()]
    assert [ln["id"] for ln in lines] == [1, 2]
    payload = json.loads(lines[0]["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert ">=" in payload["body"] and "<->" in payload["body"]
    assert "node_count" in lines[1]["result"]["content"][0]["text"]


def test_fr7908_get_skill_each_fleet_root(tmp_path: Path):
    names = ("seat", "bob", "common", "user")
    roots = []
    skills = []
    for name in names:
        root = tmp_path / name / ".grok" / "skills"
        roots.append(root)
        skills.append(_skill(root, "skill-" + name))
    server = mcp.SkillDagServer(roots=roots, max_bytes=65536)
    for skill in skills:
        got = server.get_skill(str(skill))
        assert got["ok"] is True
        assert ">=" in got["body"]


def test_fr7908_configure_stdio_utf8(monkeypatch):
    seen = {}

    class _Stream:
        def __init__(self, name):
            self.name = name

        def reconfigure(self, **kwargs):
            seen[self.name] = kwargs

    monkeypatch.setattr(sys, "stdin", _Stream("stdin"))
    monkeypatch.setattr(sys, "stdout", _Stream("stdout"))
    monkeypatch.setattr(sys, "stderr", _Stream("stderr"))
    mcp.configure_stdio_utf8()
    assert seen["stdin"]["encoding"] == "utf-8"
    assert seen["stdout"] == {"encoding": "utf-8", "errors": "backslashreplace"}
    assert seen["stderr"]["encoding"] == "utf-8"


def test_fr7908_tool_exception_is_auto_reported(tmp_path: Path, monkeypatch):
    reported = []

    class _Boom(mcp.SkillDagServer):
        def get_skill(self, path: str) -> dict:
            raise RuntimeError("boom")

    monkeypatch.setattr(mcp, "_AUTO_REPORT", reported.append)
    server = _Boom(roots=[tmp_path], max_bytes=1000)
    inf = io.StringIO(_tools_call(1, "get_skill", {"path": "x"}) + "\n")
    out = io.StringIO()
    mcp.serve_stdio(server, inf, out)
    assert reported and isinstance(reported[0], RuntimeError)
    assert json.loads(out.getvalue().splitlines()[0])["error"]["code"] == -32603


def test_fr7908_preflight_restarts_once_then_gives_up():
    calls = {"restart": 0}

    def probe() -> bool:
        return False

    def restart() -> None:
        calls["restart"] += 1

    decision = bw.skill_dag_preflight(probe, restart)
    assert decision == {
        "action": "giveup",
        "restarted": True,
        "reason": "skill_dag_down",
    }
    assert calls["restart"] == 1


def test_fr7908_preflight_healthy_skips_restart():
    calls = {"restart": 0}
    decision = bw.skill_dag_preflight(lambda: True, lambda: calls.__setitem__("restart", 1))
    assert decision["action"] == "continue"
    assert decision["restarted"] is False
    assert calls["restart"] == 0


def test_fr7908_preflight_recovers_after_one_restart():
    seen = {"n": 0}

    def probe() -> bool:
        seen["n"] += 1
        return seen["n"] > 1

    decision = bw.skill_dag_preflight(probe, lambda: None)
    assert decision["action"] == "continue"
    assert decision["restarted"] is True


def test_fr7908_preflight_probe_exception_is_down():
    def boom() -> bool:
        raise RuntimeError("no python")

    decision = bw.skill_dag_preflight(boom, lambda: None)
    assert decision["action"] == "giveup"
    assert decision["reason"] == "skill_dag_down"


def test_fr7908_giveup_line_shape():
    assert (
        bw.skill_dag_down_giveup_line("FR SimonBarnett/bobiverse#7908")
        == "GIVEUP FR SimonBarnett/bobiverse#7908 skill_dag_down"
    )
    assert bw.skill_dag_down_giveup_line("") == "GIVEUP job skill_dag_down"


def _fake_proc(returncode: int, stdout: str = "", stderr: str = ""):
    class _P:
        pass

    p = _P()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _probe_workspace(tmp_path: Path, *, job_skill: bool = True) -> Path:
    cwd = tmp_path / "worker"
    cwd.mkdir()
    script = tmp_path / "bob" / "scripts" / "skill_dag_mcp.py"
    script.parent.mkdir(parents=True)
    script.write_text("# stub\n", encoding="utf-8")
    if job_skill:
        _skill(cwd / ".grok" / "skills", "bobiverse-bob-job-fr")
    else:
        _skill(cwd / ".grok" / "skills", "some-other-skill")
    return cwd


def test_fr7908_probe_runs_get_skill_on_job_skill(tmp_path: Path):
    cwd = _probe_workspace(tmp_path)
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = list(argv)
        return _fake_proc(0, json.dumps({"ok": True, "body": NON_CP1252}))

    result = bw.probe_skill_dag_mcp_cli(
        str(cwd), job_worktree=str(cwd), job_key="FR SimonBarnett/bobiverse#7908", runner=runner
    )
    assert result == {"ok": True, "reason": ""}
    assert "--once" in seen["argv"] and "get_skill" in seen["argv"]
    assert any(str(a).endswith("bobiverse-bob-job-fr\\SKILL.md") or str(a).endswith("bobiverse-bob-job-fr/SKILL.md") for a in seen["argv"])


def test_fr7908_probe_nonzero_exit_is_down(tmp_path: Path):
    cwd = _probe_workspace(tmp_path)
    result = bw.probe_skill_dag_mcp_cli(
        str(cwd), job_key="FR x#1", runner=lambda argv, **kw: _fake_proc(3, "", "UnicodeEncodeError")
    )
    assert result["ok"] is False
    assert result["reason"] == "exit-3"


def test_fr7908_probe_falls_back_to_status_without_job_skill(tmp_path: Path, monkeypatch):
    cwd = _probe_workspace(tmp_path, job_skill=False)
    monkeypatch.setattr(bw, "skill_dag_job_skill_md", lambda *_a, **_k: None)
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = list(argv)
        return _fake_proc(0, json.dumps({"node_count": 4}))

    result = bw.probe_skill_dag_mcp_cli(str(cwd), job_key="FR x#1", runner=runner)
    assert result == {"ok": True, "reason": ""}
    assert "status" in seen["argv"] and "get_skill" not in seen["argv"]


def test_fr7908_worker_inject_line_gates_on_preflight():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    i = src.index("def _inject_line")
    j = src.find("\n    def ", i + 1)
    body = src[i:j]
    assert "_skill_dag_preflight_for_opencode" in body
    assert "skill_dag_down_giveup_line" in body
    assert "JobContextRefused" in body
