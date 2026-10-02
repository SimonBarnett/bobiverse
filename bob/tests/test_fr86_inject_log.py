"""FR #86: worker.log must keep the full relay inject line; last-from.txt holds the complete FROM payload."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_format_from_keeps_long_assign_rest():
    rest = (
        "marchhare-34208: MRB test-only SimonBarnett/none#0 "
        "https://example.invalid/pull/0 - reply with just ACK then DONE after review notes"
    )
    line = bw.format_from("Jeeves", "#marchhare", rest)
    assert line.startswith("FROM Jeeves #marchhare ")
    assert "https://example.invalid/pull/0" in line
    assert "reply with just ACK" in line
    assert "review notes" in line


def test_relay_logs_full_inject_and_writes_last_from(tmp_path: Path):
    logs: list[str] = []
    got: list[str] = []

    def inject(line: str) -> bool:
        got.append(line)
        return True

    long_rest = (
        "marchhare-34208: MRB test-only SimonBarnett/agentic_fomprep#99 "
        "https://github.com/SimonBarnett/agentic_fomprep/pull/12 "
        "- reply with just ACK FR then implement; include evidence block in PR body"
    )
    assert len("relay: injected " + bw.format_from("Jeeves", "#marchhare", long_rest)) > 120

    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    relay.set_target(inject)
    status = relay.deliver("Jeeves", "#marchhare", long_rest)
    assert status == "injected"
    assert len(got) == 1
    assert "agentic_fomprep/pull/12" in got[0]
    assert "evidence block" in got[0]

    # worker.log line must not be cut at 120 chars
    hit = [m for m in logs if m.startswith("relay: injected ")]
    assert hit, logs
    assert hit[0] == "relay: injected " + got[0]
    assert "evidence block" in hit[0]

    last = tmp_path / "last-from.txt"
    assert last.is_file()
    body = last.read_text(encoding="utf-8")
    assert body == got[0] + "\n"
    assert "agentic_fomprep" in body
    # no UTF-8 BOM
    raw = last.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
