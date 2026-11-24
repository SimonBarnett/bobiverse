# -*- coding: utf-8 -*-
"""FR #9862: one canonical ear outbox cursor (outbox.txt.pos); migrate/delete legacy outbox.pos."""
from __future__ import annotations

from pathlib import Path

import irc_agent


def test_fr9862_outbox_pos_path_is_name_plus_pos(tmp_path: Path) -> None:
    out = tmp_path / "outbox.txt"
    assert irc_agent.outbox_pos_path(out) == tmp_path / "outbox.txt.pos"
    assert irc_agent.legacy_outbox_pos_path(out) == tmp_path / "outbox.pos"
    bare = tmp_path / "outbox"
    assert irc_agent.outbox_pos_path(bare) == tmp_path / "outbox.pos"
    assert irc_agent.legacy_outbox_pos_path(bare) is None


def test_fr9862_load_prefers_canonical_when_legacy_stale_zero(tmp_path: Path) -> None:
    """Live redqueen: outbox.pos=0 stale; outbox.txt.pos at EOF — must not replay."""
    out = tmp_path / "outbox.txt"
    body = b"PRIVMSG #redqueen :ACK FR x\n" * 40
    out.write_bytes(body)
    (tmp_path / "outbox.pos").write_text("0\n", encoding="utf-8")
    (tmp_path / "outbox.txt.pos").write_text(f"{len(body)}\n", encoding="utf-8")

    pos = irc_agent.load_outbox_pos(out)
    assert pos == len(body)
    assert (tmp_path / "outbox.txt.pos").is_file()
    assert not (tmp_path / "outbox.pos").exists(), "legacy outbox.pos must be removed"


def test_fr9862_migrate_legacy_only_to_canonical(tmp_path: Path) -> None:
    out = tmp_path / "outbox.txt"
    out.write_bytes(b"PRIVMSG #x :a\nPRIVMSG #x :b\n")
    (tmp_path / "outbox.pos").write_text("14\n", encoding="utf-8")

    pos = irc_agent.load_outbox_pos(out)
    assert pos == 14
    assert (tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip() == "14"
    assert not (tmp_path / "outbox.pos").exists()


def test_fr9862_legacy_zero_with_body_seals_eof(tmp_path: Path) -> None:
    """Legacy cursor reset to 0 while body remains — seal EOF (no full replay)."""
    out = tmp_path / "outbox.txt"
    body = b"PRIVMSG #x :old-1\nPRIVMSG #x :old-2\n"
    out.write_bytes(body)
    (tmp_path / "outbox.pos").write_text("0\n", encoding="utf-8")

    pos = irc_agent.load_outbox_pos(out)
    assert pos == len(body)
    assert (tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip() == str(len(body))
    assert not (tmp_path / "outbox.pos").exists()


def test_fr9862_save_writes_canonical_and_drops_legacy(tmp_path: Path) -> None:
    out = tmp_path / "outbox.txt"
    out.write_bytes(b"PRIVMSG #x :hi\n")
    (tmp_path / "outbox.pos").write_text("0\n", encoding="utf-8")

    irc_agent.save_outbox_pos(out, 15)
    assert (tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip() == "15"
    assert not (tmp_path / "outbox.pos").exists()
    assert irc_agent.load_outbox_pos(out) == 15


def test_fr9862_missing_pos_still_zero_without_inventing_eof(tmp_path: Path) -> None:
    """No cursor files → 0 (JOIN / first drain). Do not invent EOF on empty migrate."""
    out = tmp_path / "outbox.txt"
    out.write_bytes(b"PRIVMSG #x :new\n")
    assert irc_agent.load_outbox_pos(out) == 0
    assert not (tmp_path / "outbox.txt.pos").exists()
    assert not (tmp_path / "outbox.pos").exists()


def test_fr9862_docs_name_canonical_cursor() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "bob/docs/bob-ear.md").read_text(encoding="utf-8")
    assert "outbox.txt.pos" in text
    assert "FR #9862" in text
