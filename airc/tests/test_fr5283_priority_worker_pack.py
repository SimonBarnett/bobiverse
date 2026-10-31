"""FR #5283: service-owned Priority Web SDK worker packaging."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

WORKER = ROOT / "airc/priority-worker/priority_worker.py"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
ALLOW = ROOT / "airc/tests/test_fr3514_client_allowlist_payload.py"


def test_fr5283_layout_no_peer_exe():
    assert WORKER.is_file()
    assert (ROOT / "airc/priority-worker/README.md").is_file()
    assert (ROOT / "airc/priority-worker/package.json").is_file()
    assert not list(ROOT.rglob("PriorityClient.exe"))
    raw = WORKER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_fr5283_worker_refuses_unless_airc_owned():
    py = sys.executable
    bare = subprocess.run(
        [py, str(WORKER)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        cwd=str(ROOT),
    )
    assert bare.returncode == 2
    assert "refuse" in (bare.stderr or "").lower()
    owned = subprocess.run(
        [py, str(WORKER), "--from-airc"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        cwd=str(ROOT),
    )
    assert owned.returncode == 0
    assert "owned=airc" in (owned.stdout or "")


def test_fr5283_console_argv_uses_from_airc():
    import airc_console as ac

    argv = ac.priority_worker_argv(ROOT / "airc")
    assert argv[-1] == "--from-airc"
    assert argv[-2].endswith("priority_worker.py")


def test_fr5283_pack_and_client_keep_worker():
    pack = PACK.read_text(encoding="utf-8")
    assert "priority-worker" in pack
    assert "FR #5283" in pack
    allow = ALLOW.read_text(encoding="utf-8")
    assert r"airc\priority-worker\priority_worker.py" in allow
