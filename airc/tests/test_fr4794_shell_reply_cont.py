"""FR #4794: CONT/RESUME pages after FR #4790 truncate without re-running the shell."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac


def _big_outcome(job_id: str = "aabbccdd", n: int = 200) -> ac.ShellOutcome:
    lines = [f"LINE{i:04d}-" + ("B" * 280) for i in range(n)]
    return ac.ShellOutcome(job_id=job_id, exit_code=0, stdout="\n".join(lines), stderr="")


def test_fr4794_truncate_marker_mentions_cont():
    records = ac.format_shell_replies(_big_outcome(), max_irc_lines=16)
    joined = "\n".join(records)
    assert "output truncated" in joined.lower()
    assert "CONT id=aabbccdd" in joined
    assert "FR #4794" in joined or "fr #4794" in joined.lower()
    assert records[-1] == "DONE id=aabbccdd exit=0"


def test_fr4794_format_shell_replies_ex_pages():
    out = _big_outcome()
    page1 = ac.format_shell_replies_ex(out, max_irc_lines=16)
    assert page1.next_offset is not None
    assert page1.next_offset == 16
    assert page1.lines[-1] == "DONE id=aabbccdd exit=0"
    assert any("CONT id=aabbccdd" in r for r in page1.lines)

    page2 = ac.format_shell_replies_ex(out, offset=page1.next_offset, max_irc_lines=16)
    assert page2.next_offset is not None
    bodies1 = [r for r in page1.lines if r.startswith("out ")]
    bodies2 = [r for r in page2.lines if r.startswith("out ")]
    assert bodies1
    assert bodies2
    assert bodies1[0] != bodies2[0]

    # Drain remaining pages
    off = page2.next_offset
    last = page2
    guard = 0
    while off is not None and guard < 50:
        last = ac.format_shell_replies_ex(out, offset=off, max_irc_lines=16)
        off = last.next_offset
        guard += 1
    assert last.next_offset is None
    assert "output truncated" not in "\n".join(last.lines).lower()
    assert last.lines[-1] == "DONE id=aabbccdd exit=0"


def test_fr4794_shell_runner_cont_without_rerun(monkeypatch):
    emitted: list[tuple[str, str]] = []
    runs: list[str] = []

    def _fake_run(req, timeout_s=None, cwd=None):
        runs.append(req.body)
        return _big_outcome(job_id=req.job_id, n=80)

    monkeypatch.setattr(ac, "run_shell_request", _fake_run)
    runner = ac.ShellJobRunner(
        on_reply=lambda nick, line: emitted.append((nick, line)),
        wait=True,
        timeout_s=5,
    )
    cmd = "id=aabbccdd Write-Output x"
    runner.start("op", cmd)
    assert len(runs) == 1
    first = [ln for nick, ln in emitted if nick == "op"]
    assert any("CONT id=aabbccdd" in ln for ln in first)
    assert first[-1] == "DONE id=aabbccdd exit=0"

    emitted.clear()
    ok = runner.continue_replies("op", "aabbccdd")
    assert ok is True
    assert len(runs) == 1  # no re-run
    second = [ln for nick, ln in emitted if nick == "op"]
    assert second[-1] == "DONE id=aabbccdd exit=0"
    assert any(ln.startswith("out id=aabbccdd") for ln in second)


def test_fr4794_cont_unknown_id_fail_closed():
    emitted: list[str] = []
    runner = ac.ShellJobRunner(on_reply=lambda nick, line: emitted.append(line), wait=False)
    ok = runner.continue_replies("op", "deadbeef")
    assert ok is False
    assert any("no resume" in ln.lower() or "unknown" in ln.lower() for ln in emitted)
    assert emitted[-1] == "DONE id=deadbeef exit=1"


def test_fr4794_parse_cont_request():
    assert ac.parse_cont_request("CONT id=aabbccdd") == ("aabbccdd", None)
    assert ac.parse_cont_request("RESUME id=aabbccdd offset=48") == ("aabbccdd", 48)
    assert ac.parse_cont_request("id=aabbccdd CONT") == ("aabbccdd", None)
    assert ac.parse_cont_request("STATUS") is None


def test_fr4794_docs_mention_cont():
    root = Path(__file__).resolve().parents[1]
    docs = [
        root / "docs" / "airc-remote-control.md",
        root / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md",
    ]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in docs if p.is_file())
    assert "FR #4794" in blob or "4794" in blob
    assert "CONT" in blob
