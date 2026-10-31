"""FR #5196: stale agent.quit.request must not quit the ear on next start."""
from __future__ import annotations

import time
from pathlib import Path

import agent_control as ac


def test_stale_quit_request_removed_not_acted(tmp_path: Path):
    started = time.time()
    old = started - 4.5 * 3600
    p = ac.quit_request_path(tmp_path)
    p.write_text(f"{int(old)} tray-stop\n", encoding="utf-8")
    reason = ac.consume_quit_request(tmp_path, ignore_before=started, now=started)
    assert reason is None
    assert not p.exists()


def test_live_quit_request_still_consumed(tmp_path: Path):
    started = time.time() - 10
    now = time.time()
    ac.request_agent_quit(tmp_path, "tray-stop")
    reason = ac.consume_quit_request(tmp_path, ignore_before=started, now=now)
    assert reason == "tray-stop"
    assert not ac.quit_request_path(tmp_path).exists()


def test_ttl_drops_ancient_file_without_ignore_before(tmp_path: Path):
    now = 1_700_000_000.0
    p = ac.quit_request_path(tmp_path)
    p.write_text(f"{int(now - 400)} leftover\n", encoding="utf-8")
    reason = ac.consume_quit_request(tmp_path, now=now, ttl_s=90)
    assert reason is None
    assert not p.exists()
