# -*- coding: utf-8 -*-
"""FR #8218: build-bob-worker artifact manifest lists per-file SHA-256."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

SCRIPTS = ROOT / "bob" / "scripts"
WF = ROOT / ".github" / "workflows" / "build-bob-worker.yml"
DOCS = ROOT / "bob" / "docs" / "bob-worker.md"
MOD = SCRIPTS / "artifact_manifest.py"


def _mod():
    sys.path.insert(0, str(SCRIPTS))
    import artifact_manifest as m  # noqa: WPS433

    return m


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_fr8218_module_and_workflow_pins():
    assert MOD.is_file()
    text = WF.read_text(encoding="utf-8")
    assert "artifact_manifest.py" in text
    assert "write --stage" in text or "artifact_manifest.py\" write" in text.replace("'", '"')
    assert "verify --stage" in text
    # Must not keep the provenance-only alias copy as the sole manifest.
    assert "Copy-Item -LiteralPath (Join-Path $stage \"provenance.txt\") -Destination (Join-Path $stage \"manifest.txt\")" not in text
    assert "bob/tests/test_fr8218_worker_artifact_manifest.py" in text
    assert "GITHUB_RUN_ID" in text or "github-run-id" in text
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #8218" in docs
    assert "manifest.txt" in docs


def test_fr8218_write_lists_every_payload_file(tmp_path: Path):
    m = _mod()
    stage = tmp_path / "art"
    scripts = stage / "scripts"
    scripts.mkdir(parents=True)
    exe = b"MZ" + b"\0" * 64
    (stage / "bob-worker.exe").write_bytes(exe)
    (stage / "bob-worker.exe.sha256").write_text(
        "%s  bob-worker.exe\n" % _sha(exe), encoding="ascii"
    )
    (stage / "provenance.txt").write_text(
        "source_commit=abc123\nworkflow_commit=abc123\n", encoding="ascii"
    )
    (scripts / "opencode_turn_guard.py").write_text("# ship\n", encoding="utf-8")
    (scripts / "Clear-BobiverseJobWorktrees.ps1").write_text("# clear\n", encoding="utf-8")
    # Stale provenance-alias must be replaced, not hashed as payload.
    (stage / "manifest.txt").write_text("source_commit=OLD\n", encoding="ascii")

    out = m.write_manifest(
        stage,
        source_commit="abc123deadbeef",
        workflow_commit="abc123deadbeef",
        github_run_id="44335804303",
        github_run_attempt="1",
        product="bob-worker",
        fr="8218",
    )
    assert out == stage / "manifest.txt"
    text = out.read_text(encoding="ascii")
    assert "source_commit=abc123deadbeef" in text
    assert "github_run_id=44335804303" in text
    assert "file_count=5" in text
    assert "bob-worker.exe\t" in text
    assert "scripts/opencode_turn_guard.py\t" in text
    assert "provenance.txt\t" in text
    # Manifest leaf is not listed as its own payload row.
    assert not any(
        line.startswith("manifest.txt\t") for line in text.splitlines() if "\t" in line
    )
    header = m.verify_manifest(stage)
    assert header["source_commit"] == "abc123deadbeef"
    assert header["file_count"] == "5"


def test_fr8218_verify_fails_on_missing_hash_mismatch_and_extra(tmp_path: Path):
    m = _mod()
    stage = tmp_path / "art"
    stage.mkdir()
    (stage / "a.bin").write_bytes(b"one")
    (stage / "b.bin").write_bytes(b"two")
    m.write_manifest(stage, source_commit="s1", workflow_commit="s1")

    # Missing file
    (stage / "a.bin").unlink()
    with pytest.raises(SystemExit, match="missing"):
        m.verify_manifest(stage)
    (stage / "a.bin").write_bytes(b"one")

    # Hash mismatch
    (stage / "b.bin").write_bytes(b"TWO")
    with pytest.raises(SystemExit, match="mismatch"):
        m.verify_manifest(stage)
    (stage / "b.bin").write_bytes(b"two")

    # Extra unlisted file
    (stage / "c.bin").write_bytes(b"three")
    with pytest.raises(SystemExit, match="not in manifest"):
        m.verify_manifest(stage)


def test_fr8218_cli_write_and_verify(tmp_path: Path):
    m = _mod()
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "bob-worker.exe").write_bytes(b"MZ-cli")
    (stage / "provenance.txt").write_text("source_commit=cli\n", encoding="ascii")
    assert (
        m.main(
            [
                "write",
                "--stage",
                str(stage),
                "--source-commit",
                "cli",
                "--github-run-id",
                "9",
            ]
        )
        == 0
    )
    assert (stage / "manifest.txt").is_file()
    assert m.main(["verify", "--stage", str(stage)]) == 0
