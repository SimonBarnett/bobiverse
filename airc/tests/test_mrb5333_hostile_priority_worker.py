"""MRB #5333 hostile pins for FR #5283 service-owned Priority worker."""
from __future__ import annotations

import os
import subprocess
import sys

from repo_layout import ROOT

WORKER = ROOT / "airc" / "priority-worker" / "priority_worker.py"
ISO = ROOT / "airc" / "docs" / "airc-isolated-workers-in-service.md"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def test_mrb5333_env_owned_and_no_peer_exe():
    env = os.environ.copy()
    env["AIRC_PRIORITY_OWNED"] = "1"
    p = subprocess.run(
        [sys.executable, str(WORKER)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        env=env,
        cwd=str(ROOT),
    )
    assert p.returncode == 0
    assert "owned=airc" in (p.stdout or "")
    assert not list(ROOT.rglob("PriorityClient.exe"))


def test_mrb5333_docs_and_pack_in_tree():
    iso = ISO.read_text(encoding="utf-8")
    assert "airc/priority-worker" in iso
    assert "FR #5283" in iso
    assert "PriorityClient.exe" in iso
    pack = PACK.read_text(encoding="utf-8")
    assert "not PriorityClient.exe" in pack or "not a standalone" in pack.lower()
    import airc_console as ac

    argv = ac.priority_worker_argv(ROOT / "airc")
    assert "--from-airc" in argv
    assert "priority_worker.py" in argv[-2].replace("/", "\\")
