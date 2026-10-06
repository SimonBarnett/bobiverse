"""FR #2655: send_privmsg test stubs must accept flood= kwargs.

After #2649/#2652, drain_out_queue calls send_privmsg(..., flood=flood).
A 2-arg lambda stub raises TypeError and reds the airc suite.
"""
from __future__ import annotations

import re
from pathlib import Path

import airc_console_service as svc


def test_fr2655_send_privmsg_signature_accepts_flood():
    import inspect
    sig = inspect.signature(svc.AircConsoleService.send_privmsg)
    assert "flood" in sig.parameters


def test_fr2655_no_two_arg_send_privmsg_lambda_stubs():
    """Guard: airc/tests must not monkeypatch send_privmsg with a 2-arg-only lambda."""
    root = Path(__file__).resolve().parent
    bad: list[str] = []
    pat = re.compile(r"send_privmsg\s*=\s*lambda\s+target\s*,\s*text\s*:")
    for path in sorted(root.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line) and "**" not in line:
                bad.append(f"{path.name}:{i}:{line.strip()}")
    assert bad == [], "2-arg send_privmsg stubs break flood= (FR #2655):\n" + "\n".join(bad)
