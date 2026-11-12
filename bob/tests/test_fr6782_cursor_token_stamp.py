"""FR #6782 / FR-002: Cursor CLI stamps measured tokens or tokens=unknown."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import done_usage  # noqa: E402


def _counts_doc():
    return {
        "model": "cursor/composer-1",
        "usage": {
            "input_tokens": 11,
            "output_tokens": 3,
            "cache_read_tokens": 2,
        },
    }


def test_fr6782_counts_fixture_stamps_fields_and_model(tmp_path: Path):
    path = tmp_path / "cursor-usage.json"
    path.write_text(json.dumps(_counts_doc()), encoding="utf-8")
    u = done_usage.measure_seat_usage("cursor", cursor_usage_path=path)
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens_in=11" in stamp
    assert "tokens_out=3" in stamp
    assert "tokens_cached=2" in stamp
    assert "model=cursor/composer-1" in stamp
    assert "tokens=unknown" not in stamp
    assert "tokens_in=0" not in stamp


def test_fr6782_missing_file_is_unknown_not_zero(tmp_path: Path):
    u = done_usage.measure_seat_usage(
        "cursor", cursor_usage_path=tmp_path / "nope-cursor-usage.json"
    )
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens=unknown" in stamp
    assert "tokens_in=0" not in stamp
    assert "tokens_out=0" not in stamp


def test_fr6782_zero_token_store_is_unknown_not_zero(tmp_path: Path):
    path = tmp_path / "cursor-usage.json"
    path.write_text(
        json.dumps(
            {
                "model": "cursor/composer-1",
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("cursor", cursor_usage_path=path)
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens=unknown" in stamp
    assert "tokens_in=0" not in stamp


def test_fr6782_chat_dir_nonzero_used_when_fixture_missing(tmp_path: Path):
    chat = tmp_path / "chat"
    chat.mkdir()
    (chat / "usage.json").write_text(json.dumps(_counts_doc()), encoding="utf-8")
    u = done_usage.measure_seat_usage(
        "cursor",
        cursor_usage_path=tmp_path / "missing.json",
        cursor_chat_dir=chat,
    )
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens_in=11" in stamp
    assert "model=cursor/composer-1" in stamp


def test_fr6782_chat_dir_zero_or_empty_is_unknown(tmp_path: Path):
    chat = tmp_path / "chat"
    chat.mkdir()
    (chat / "store.json").write_text(
        json.dumps({"usage": {"input_tokens": 0, "output_tokens": 0}}),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("cursor", cursor_chat_dir=chat)
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens=unknown" in stamp
    assert "tokens_in=0" not in stamp
    empty = tmp_path / "empty-chat"
    empty.mkdir()
    (empty / "notes.txt").write_text("no tokens", encoding="utf-8")
    u2 = done_usage.measure_seat_usage("cursor", cursor_chat_dir=empty)
    stamp2 = done_usage.format_done_usage_suffix(u2, worker_build="unknown")
    assert "tokens=unknown" in stamp2
    assert "tokens_in=0" not in stamp2
