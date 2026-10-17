"""Cursor seats: verify the pasted Jeeves line was submitted (prompt_history probe)."""
from __future__ import annotations

import json
import os
import time

import bob_worker as bw

LINE = "FROM Jeeves #flamingo flamingo-11232: MRB SimonBarnett/a-search#1796 https://github.com/SimonBarnett/a-search/pull/1796"


def _hist(root, entries, mtime=None):
    d = root / "ws" / "chat"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "prompt_history.json"
    f.write_text(json.dumps(entries), encoding="utf-8")
    if mtime is not None:
        os.utime(f, (mtime, mtime))
    return f


def test_cursor_probe_false_on_lone_v(tmp_path):
    t0 = time.time()
    _hist(tmp_path, ["v"])
    p = bw.make_submit_probe("cursor", text=LINE, since_wall=t0, cursor_chats_root=tmp_path)
    assert p is not None and p() is False


def test_cursor_probe_true_when_line_submitted(tmp_path):
    t0 = time.time()
    p = bw.make_submit_probe("cursor", text=LINE, since_wall=t0, cursor_chats_root=tmp_path)
    assert p() is False
    _hist(tmp_path, ["v", LINE])
    assert p() is True


def test_cursor_probe_ignores_stale_history(tmp_path):
    t0 = time.time()
    _hist(tmp_path, [LINE], mtime=t0 - 600)
    p = bw.make_submit_probe("cursor", text=LINE, since_wall=t0, cursor_chats_root=tmp_path)
    assert p() is False


def test_cursor_gap_default_and_env(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_CURSOR_SUBMIT_GAP_S", raising=False)
    assert bw._cursor_submit_gap_s() == 1.0
    monkeypatch.setenv("BOB_WORKER_CURSOR_SUBMIT_GAP_S", "0.01")
    assert bw._cursor_submit_gap_s() == 0.2


def test_verify_loop_retries_enter_until_cursor_probe(tmp_path):
    t0 = time.time()
    p = bw.make_submit_probe("cursor", text=LINE, since_wall=t0, cursor_chats_root=tmp_path)
    enters = []

    def enter(pid=0):
        enters.append(1)
        if len(enters) == 2:
            _hist(tmp_path, [LINE])
        return True

    clock = [0.0]
    res = bw.run_submit_verify_loop(
        enter_fn=enter, probe_fn=p, clock=lambda: clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        verify_s=1.0, max_retries=3, backoffs=(1.0, 1.0, 1.0),
    )
    assert res == "ok" and len(enters) == 2
