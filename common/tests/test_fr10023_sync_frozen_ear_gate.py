"""FR #10023: Sync must not overlay tip scripts when frozen bob-ear lags tip."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_layout import ROOT

import sync_frozen_ear_compose_gate as gate

SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"


def test_sync_script_wires_frozen_ear_gate():
    text = SYNC.read_text(encoding="utf-8")
    assert "sync_frozen_ear_compose_gate.py" in text
    assert "sync-skip-frozen-ear-scripts" in text
    assert "AllowFrozenEarScriptsCompose" in text


def test_gate_blocks_when_provenance_lags_tip(tmp_path: Path):
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bob-ear.exe").write_bytes(b"MZ")
    (scripts / "provenance.txt").write_text(
        "source_commit=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
        encoding="ascii",
    )
    clone = tmp_path / "clone"
    subprocess.check_call(
        ["git", "init", "-q", str(clone)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        ["git", "-C", str(clone), "commit", "--allow-empty", "-m", "tip", "-q"],
        env={**dict(__import__("os").environ), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    tip = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
    blocked, line = gate.frozen_ear_scripts_compose_blocked(install, clone)
    assert blocked is True
    assert "sync-skip-frozen-ear-scripts" in line
    assert tip[:12] in line


def test_gate_allows_matching_provenance(tmp_path: Path):
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bob-ear.exe").write_bytes(b"MZ")
    clone = tmp_path / "clone"
    subprocess.check_call(["git", "init", "-q", str(clone)])
    subprocess.check_call(
        ["git", "-C", str(clone), "commit", "--allow-empty", "-m", "tip", "-q"],
        env={**dict(__import__("os").environ), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    tip = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
    (scripts / "provenance.txt").write_text(f"source_commit={tip}\n", encoding="ascii")
    blocked, _ = gate.frozen_ear_scripts_compose_blocked(install, clone)
    assert blocked is False


def test_gate_cli_json_fail_open_without_provenance(tmp_path: Path):
    install_root = tmp_path / "i"
    scripts = install_root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bob-ear.exe").write_bytes(b"x")
    clone = tmp_path / "c"
    subprocess.check_call(["git", "init", "-q", str(clone)])
    out = subprocess.check_output(
        [
            "python",
            str(ROOT / "common" / "scripts" / "sync_frozen_ear_compose_gate.py"),
            "--install",
            str(install_root),
            "--clone",
            str(clone),
        ],
        text=True,
    )
    doc = json.loads(out)
    assert doc.get("blocked") is False