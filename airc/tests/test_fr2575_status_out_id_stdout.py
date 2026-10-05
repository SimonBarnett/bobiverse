"""FR #2575: STATUS frames body as out id= seq= so Invoke-AircRemote StdOut is non-empty."""
from __future__ import annotations

import re

import airc_jobs as jobs


_OUT_RE = re.compile(
    r"^(?P<stream>out|err)\s+id=(?P<id>[0-9a-f]+)\s+seq=(?P<seq>\d+)\s(?P<body>.*)$"
)
_DONE_RE = re.compile(r"^DONE\s+id=(?P<id>[0-9a-f]+)\s+exit=(?P<exit>-?\d+)\s*$")


def _stdout_from_replies(lines: list[str], expect_id: str) -> tuple[str, int]:
    """Minimal mirror of Invoke-AircRemote ConvertFrom-AircRemoteReply stdout join."""
    outs: list[tuple[int, str]] = []
    exit_code = None
    for ln in lines:
        m = _OUT_RE.match(ln)
        if m and m.group("id") == expect_id and m.group("stream") == "out":
            outs.append((int(m.group("seq")), m.group("body")))
            continue
        d = _DONE_RE.match(ln)
        if d and d.group("id") == expect_id:
            exit_code = int(d.group("exit"))
    outs.sort(key=lambda x: x[0])
    assert exit_code is not None, "missing DONE"
    return "\n".join(b for _, b in outs), exit_code


def test_status_with_id_yields_nonempty_stdout_machine_line(tmp_path):
    for name in ("bob", "airc", "jeeves"):
        d = tmp_path / name
        d.mkdir()
        (d / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="marchhare", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {"id": "aa1ae2e7"})
    assert lines[-1] == "DONE id=aa1ae2e7 exit=0"
    assert lines[0].startswith("out id=aa1ae2e7 seq=1 ")
    stdout, code = _stdout_from_replies(lines, "aa1ae2e7")
    assert code == 0
    assert stdout.strip() != ""
    assert "machine=marchhare" in stdout
    assert "STATUS machine=marchhare" in stdout
