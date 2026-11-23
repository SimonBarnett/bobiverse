# -*- coding: utf-8 -*-
"""FR #9239: take_outbox_records must not Path.read_bytes() a huge outbox."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import irc_agent


def test_fr9239_take_outbox_records_seeks_past_large_prefix(tmp_path: Path):
    """Drain from a near-end offset must not require loading the whole file."""
    out = tmp_path / "outbox.txt"
    # ~800 KiB of already-drained lines + two fresh lines.
    prefix = (b"PRIVMSG #x :old\n") * 50000
    fresh = b"PRIVMSG #x :new1\nPRIVMSG #x :new2\n"
    out.write_bytes(prefix + fresh)
    last = len(prefix)
    records, new_last = irc_agent.take_outbox_records(out, last, max_lines=8)
    assert len(records) == 2
    assert "new1" in records[0][0]
    assert "new2" in records[1][0]
    assert new_last == last + len(fresh)


def test_fr9239_take_outbox_records_respects_max_bytes_cap(tmp_path: Path):
    """A small max_bytes leaves incomplete / unread lines unconsumed."""
    out = tmp_path / "outbox.txt"
    line = b"PRIVMSG #x :aaaaaaaaaaaaaaaaaaaaaaaa\n"
    assert len(line) == 37
    out.write_bytes(line * 20)
    records, new_last = irc_agent.take_outbox_records(
        out, 0, max_lines=None, max_bytes=100
    )
    # 100 bytes fits two complete 37-byte lines (74); third starts but no LF in cap.
    assert len(records) == 2
    assert new_last == 74
    assert new_last < out.stat().st_size


def test_fr9239_take_outbox_records_memoryerror_soft(tmp_path: Path, capsys):
    """MemoryError during read returns empty batch; does not raise."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #x :hi\n", encoding="utf-8")

    real_open = Path.open

    def boom(self, *args, **kwargs):
        if self == out or self.name == out.name:
            raise MemoryError()
        return real_open(self, *args, **kwargs)

    with mock.patch.object(Path, "open", boom):
        records, new_last = irc_agent.take_outbox_records(out, 0, max_lines=8)
    assert records == []
    assert new_last == 0
    out_txt = capsys.readouterr().out + capsys.readouterr().err
    assert "MemoryError" in out_txt


def test_fr9239_outbox_read_max_bytes_constant():
    assert irc_agent.OUTBOX_READ_MAX_BYTES >= 64 * 1024
    assert "OUTBOX_READ_MAX_BYTES" in Path(irc_agent.__file__).read_text(
        encoding="utf-8"
    )
