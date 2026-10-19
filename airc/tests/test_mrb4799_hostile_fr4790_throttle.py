"""docs/mrb-4799 hostile pins for FR #4790 / PR #4799.

Additive: DONE after truncate, send-fail reconnect, rate caps, child FRs not claimed.
"""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_console_service as svc


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "scripts" / "airc_console_service.py"
CONSOLE = ROOT / "scripts" / "airc_console.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
DOCS = ROOT / "docs" / "airc-remote-control.md"


def test_mrb4799_truncate_always_ends_with_done():
    lines = [f"X{i}-" + ("Y" * 200) for i in range(120)]
    out = ac.ShellOutcome(job_id="cafebabe", exit_code=7, stdout="\n".join(lines), stderr="oops")
    records = ac.format_shell_replies(out, max_irc_lines=16)
    assert records[-1] == "DONE id=cafebabe exit=7"
    assert any("output truncated" in r.lower() for r in records)
    assert sum(1 for r in records if r.startswith("out ") or r.startswith("err ")) <= 18


def test_mrb4799_send_oserror_forces_reconnect(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    s = svc.AircConsoleService(args)

    class _Sock:
        def sendall(self, _data: bytes) -> None:
            raise OSError("simulated flood kill")

    s.sock = _Sock()  # type: ignore[assignment]
    try:
        s.send("PRIVMSG #tm :hi", flood=False)
        raise AssertionError("expected ConnectionError")
    except ConnectionError:
        pass
    assert s._force_reconnect is True


def test_mrb4799_rate_and_source_pins():
    assert 0 < float(svc.FLOOD_RATE_PER_S) <= 3.0
    assert float(svc.FLOOD_BURST) >= 1.0
    text = SERVICE.read_text(encoding="utf-8")
    assert "class FloodTokenBucket" in text
    assert "FR #4790" in text
    assert "_force_reconnect = True" in text
    console = CONSOLE.read_text(encoding="utf-8")
    assert "SHELL_REPLY_MAX_IRC_LINES" in console
    assert "output truncated" in console


def test_mrb4799_docs_do_not_claim_cont_resume():
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in (SKILL, DOCS) if p.is_file()
    )
    assert "FR #4790" in blob or "4790" in blob
    # Foundation must not pretend CONT/RESUME is shipped.
    assert "CONT/RESUME" not in blob.upper() or "child" in blob.lower() or "#4794" in blob
    assert "base64" in blob.lower()
    # No BEL corruption of airc paths
    raw = SKILL.read_bytes()
    assert b"\x07" not in raw
    assert "airc_console" in SKILL.read_text(encoding="utf-8")
