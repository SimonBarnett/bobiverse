"""FR #10106: inbound-transcript helpers for monitor /report 502 fallback."""
from pathlib import Path

import inbound_transcript as it


def test_parse_transcript_line_round_trip():
    line = "2026-11-24T19:23:00Z #redqueen Jeeves ACK FR SimonBarnett/bobiverse#1"
    parsed = it.parse_transcript_line(line)
    assert parsed is not None
    assert parsed["channel"] == "#redqueen"
    assert parsed["nick"] == "Jeeves"
    assert "ACK FR" in parsed["text"]


def test_files_end_with_newline():
    p = Path(it.__file__)
    assert p.read_bytes().endswith(b"\n")