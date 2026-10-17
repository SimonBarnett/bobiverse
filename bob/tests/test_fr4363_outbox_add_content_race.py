"""FR #4363: seat outbox append must tolerate concurrent drain (Add-Content race)."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import bob_worker as bw

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "common" / "scripts" / "Add-BobiverseOutboxLine.ps1"
SEAT = (
    ROOT
    / "bob"
    / "agents"
    / "worker"
    / ".grok"
    / "skills"
    / "bobiverse-worker-seat"
    / "SKILL.md"
)


def test_helper_script_exists_utf8_no_bom():
    assert HELPER.is_file(), "missing Add-BobiverseOutboxLine.ps1"
    raw = HELPER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "FileShare.ReadWrite" in text or "FileShare]::ReadWrite" in text
    assert "FR #4363" in text or "4363" in text
    assert "retry" in text.lower() or "Retries" in text


def test_append_outbox_line_python_survives_concurrent_drain(tmp_path: Path):
    path = tmp_path / "outbox.txt"
    bw.ensure_outbox(path)
    stop = threading.Event()
    errors: list[BaseException] = []

    def drainer():
        class FakeIrc:
            shop = "#marchhare"

            def say(self, target, text):
                return True

        while not stop.wait(0.02):
            try:
                bw.drain_outbox(path, FakeIrc(), lambda m: None)
            except Exception as e:  # pragma: no cover
                errors.append(e)

    t = threading.Thread(target=drainer, daemon=True)
    t.start()
    try:
        for i in range(40):
            bw.append_outbox_line(path, f"PRIVMSG #marchhare :ping-{i}")
            time.sleep(0.01)
    finally:
        stop.set()
        t.join(timeout=2)
    assert errors == []
    # Final drain should leave empty file present (FR #866).
    class FakeIrc2:
        shop = "#marchhare"

        def say(self, target, text):
            return True

    bw.drain_outbox(path, FakeIrc2(), lambda m: None)
    assert path.is_file()


def test_ps_helper_appends_under_replace_race(tmp_path: Path):
    """PowerShell helper must succeed while another process renames the outbox."""
    if not HELPER.is_file():
        return  # collected as fail by test_helper_script_exists
    path = tmp_path / "outbox.txt"
    bw.ensure_outbox(path)
    stop = threading.Event()

    def replacer():
        while not stop.wait(0.03):
            try:
                if path.is_file():
                    tmp = path.with_suffix(".sending")
                    path.replace(tmp)
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                bw.ensure_outbox(path)
            except OSError:
                bw.ensure_outbox(path)

    t = threading.Thread(target=replacer, daemon=True)
    t.start()
    try:
        for i in range(12):
            line = f"PRIVMSG #marchhare :DONE FR o/r#{i} https://example/pull/{i}"
            r = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(HELPER),
                    "-Path",
                    str(path),
                    "-Line",
                    line,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert r.returncode == 0, r.stdout + r.stderr
    finally:
        stop.set()
        t.join(timeout=2)
    assert path.is_file()


def test_worker_seat_skill_documents_fr4363_share_safe_append():
    raw = SEAT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "FR #4363" in text
    assert "FileShare.ReadWrite" in text or "Add-BobiverseOutboxLine" in text
    assert "Stream was not readable" in text or "concurrent" in text.lower()
