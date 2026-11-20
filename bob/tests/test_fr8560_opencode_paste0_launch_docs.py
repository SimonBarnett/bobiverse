"""FR #8560: OpenCode launch docs and seat log must not recommend PASTE=1."""
from __future__ import annotations

import os
from pathlib import Path

import bob_worker as bw


ROOT = Path(__file__).resolve().parents[1]


def test_fr8560_bob_worker_docs_forbid_opencode_paste1():
    text = (ROOT / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "FR #8560" in text
    assert "BOB_WORKER_INJECT_PASTE=0" in text
    assert "**Never** set `BOB_WORKER_INJECT_PASTE=1` for OpenCode" in text
    assert "Set `BOB_WORKER_INJECT_PASTE=1` to force clipboard paste" not in text
    assert "Paid OpenCode / DeepSeek launch (FR #8560)" in text
    assert "Do not relaunch with PASTE=1" in text


def test_fr8560_fr_oc_inject_cast_iron_keys_only():
    text = (ROOT / "docs" / "fr" / "opencode-seat-gaps" / "FR-OC-INJECT.md").read_text(
        encoding="utf-8"
    )
    assert "FR #8560" in text
    assert "BOB_WORKER_INJECT_PASTE=0" in text
    assert "Do **not** set `BOB_WORKER_INJECT_PASTE=1`" in text


def test_fr8560_opencode_keys_log_never_recommends_paste1(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    logs: list[str] = []
    assert bw.apply_cursor_inject_keys_default("opencode", log=logs.append) is True
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    joined = "\n".join(logs)
    assert "batched keys" in joined
    assert "PASTE=1 to paste" not in joined
    assert "FR #8560" in joined
    assert "never PASTE=1" in joined
