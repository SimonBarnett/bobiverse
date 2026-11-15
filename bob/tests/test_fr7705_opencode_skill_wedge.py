"""FR #7705: skill-dag drop and identical tool-call wedge."""
from __future__ import annotations

import io
import json

import skill_dag_mcp as mcp
from opencode_tool_wedge import (
    after_skill_dag_drop,
    note_identical_tool_call,
    recovery_keeps_seat_kind,
    report_wedge,
)


class _Boom(mcp.SkillDagServer):
    def get_skill(self, path: str) -> dict:
        raise RuntimeError("connection-drop")


def test_fr7705_stdio_survives_a_tool_exception():
    server = _Boom(roots=[], max_bytes=1000)
    inf = io.StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "get_skill", "arguments": {"path": "x"}},
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "status", "arguments": {}},
                    }
                ),
                "",
            ]
        )
    )
    out = io.StringIO()
    mcp.serve_stdio(server, inf, out)
    lines = [json.loads(ln) for ln in out.getvalue().splitlines() if ln.strip()]
    assert lines[0]["error"]["code"] == -32000
    assert "result" in lines[1]
    assert lines[1]["id"] == 2


def test_fr7705_drop_reconnects_then_gives_up_without_loop():
    first = after_skill_dag_drop(retries_left=1, skill_loaded=False)
    assert first["action"] == "reconnect"
    assert first["loop"] is False
    second = after_skill_dag_drop(retries_left=0, skill_loaded=False)
    assert second["action"] == "giveup"
    assert second["report"] is True
    assert second["loop"] is False
    loaded = after_skill_dag_drop(retries_left=0, skill_loaded=True)
    assert loaded["action"] == "continue"


def test_fr7705_three_identical_calls_are_a_wedge():
    recent: list[str] = []
    args = {"path": "customize-opencode"}
    a = note_identical_tool_call(recent, "Skill", args)
    b = note_identical_tool_call(recent, "Skill", args)
    assert a["wedge"] is False and b["wedge"] is False
    c = note_identical_tool_call(recent, "Skill", args)
    assert c["wedge"] is True
    assert c["action"] == "report-and-giveup"
    assert c["loop"] is False
    different = note_identical_tool_call(recent, "Skill", {"path": "other"})
    assert different["wedge"] is False


def test_fr7705_wedge_report_keeps_opencode_kind():
    seen: list[dict] = []
    body = report_wedge(
        seen.append,
        reason="skill-dag connection closed",
        signature="Skill customize-opencode",
        seat_kind="OpenCode",
    )
    assert seen == [body]
    assert body["seat_kind"] == "opencode"
    assert recovery_keeps_seat_kind("OpenCode") == "opencode"
    assert body["action"] == "giveup"
