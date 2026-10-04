"""FR #1993: jeeves.exe WP0/WP1 foundation — docs, in-proc lock, self-test, HTTP thread."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

import gitclaim
import jeeves_locks
import jeeves_main

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr1993_wp0_doc_acceptance_phrases():
    text = DOC.read_text(encoding="utf-8")
    _no_bom(DOC)
    assert "1993" in text
    assert "jeeves.exe" in text
    assert "chair + BobCallback" in text or "Chair + BobCallback" in text
    assert "self-test" in text
    assert ":7700" in text or "7700" in text
    assert "require_machine: ionos" in text or "require_machine" in text
    for metric in ("E1", "E2", "E3", "E4", "E5"):
        assert metric in text
    assert "WP0" in text and "WP1" in text
    assert "keep seats busy" in text.lower() or "clear_seat_doing" in text
    assert "BobIrcd" in text
    assert text.encode("utf-8").endswith(b"\n")


def test_fr1993_inproc_queue_lock_skips_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    jeeves_locks.disable_inproc_locks()
    jeeves_locks.enable_inproc_locks()
    try:
        assert jeeves_locks.inproc_queue_lock() is not None
        order: list[str] = []

        def other():
            with gitclaim._lock(tmp_path):
                order.append("b")

        with gitclaim._lock(tmp_path):
            order.append("a")
            t = threading.Thread(target=other)
            t.start()
            time.sleep(0.05)
            assert not (tmp_path / gitclaim.LOCK_NAME).exists()
        t.join(timeout=2)
        assert order == ["a", "b"]
    finally:
        jeeves_locks.disable_inproc_locks()


def test_fr1993_self_test_json(tmp_path):
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code2 = jeeves_main.run_self_test(home=tmp_path, as_json=True)
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["fr"] == 1993
    assert payload["exit"] == code2
    assert code2 in (0, 1, 2)
    assert "errors" in payload


def test_fr1993_http_thread_health(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    jeeves_locks.disable_inproc_locks()
    jeeves_locks.enable_inproc_locks()
    t, httpd = jeeves_main.start_http_thread(tmp_path, host="127.0.0.1", port=0)
    host, port = httpd.server_address[:2]
    try:
        url = f"http://{host}:{port}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status in (200, 204)
    finally:
        httpd.shutdown()
        t.join(timeout=2)
        jeeves_locks.disable_inproc_locks()


def test_fr1993_parse_http_bind():
    assert jeeves_main.parse_http_bind("127.0.0.1:7700") == ("127.0.0.1", 7700)
    assert jeeves_main.parse_http_bind("7700")[1] == 7700


def test_fr1993_mutex_name_stable(tmp_path):
    a = jeeves_locks.mutex_name_for_home(tmp_path)
    b = jeeves_locks.mutex_name_for_home(tmp_path)
    assert a == b
    assert a.startswith("Global\\BobiverseJeeves-")
