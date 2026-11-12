"""MRB #6811 hostile pins for FR #6782 Cursor token stamp."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import done_usage  # noqa: E402


def test_mrb6811_fixture_wins_over_chat_dir(tmp_path: Path):
    fx = tmp_path / "cursor-usage.json"
    fx.write_text(
        json.dumps(
            {
                "model": "cursor/fixture-model",
                "usage": {
                    "input_tokens": 9,
                    "output_tokens": 1,
                    "cache_read_tokens": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    chat = tmp_path / "chat"
    chat.mkdir()
    (chat / "usage.json").write_text(
        json.dumps(
            {
                "model": "cursor/live-model",
                "usage": {
                    "input_tokens": 99,
                    "output_tokens": 99,
                    "cache_read_tokens": 99,
                },
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage(
        "cursor", cursor_usage_path=fx, cursor_chat_dir=chat
    )
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens_in=9" in stamp
    assert "model=cursor/fixture-model" in stamp
    assert "tokens_in=99" not in stamp


def test_mrb6811_skips_identity_json_in_chat_dir(tmp_path: Path):
    chat = tmp_path / "chat"
    chat.mkdir()
    (chat / "identity.json").write_text(
        json.dumps(
            {
                "model": "cursor/secret-store",
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 4,
                    "cache_read_tokens": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("cursor", cursor_chat_dir=chat)
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens=unknown" in stamp
    assert "tokens_in=50" not in stamp


def test_mrb6811_jsonl_nonzero_is_measured(tmp_path: Path):
    chat = tmp_path / "chat"
    chat.mkdir()
    (chat / "events.jsonl").write_text(
        json.dumps({"usage": {"input_tokens": 7, "output_tokens": 2}}) + "\n",
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage(
        "cursor",
        cursor_usage_path=tmp_path / "missing.json",
        cursor_chat_dir=chat,
    )
    stamp = done_usage.format_done_usage_suffix(u, worker_build="unknown")
    assert "tokens_in=7" in stamp
    assert "tokens_out=2" in stamp
    assert "tokens=unknown" not in stamp


def test_mrb6811_worker_wires_cursor_chat_dir():
    src = (
        Path(__file__).resolve().parents[2] / "bob" / "scripts" / "bob_worker.py"
    ).read_text(encoding="utf-8")
    assert "cursor_chat_dir" in src
    assert "BOB_CURSOR_USAGE_PATH" in src
