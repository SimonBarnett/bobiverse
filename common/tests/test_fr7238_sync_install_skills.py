"""FR #7238: overlay origin skills into a dirty install; skip mid-job."""
from __future__ import annotations

import subprocess
from pathlib import Path

import bobreport
import sync_install_skills as sis


def _git(cwd: Path, *args: str) -> None:
    r = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout


def _init_pair(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-b", "main")
    _git(origin, "config", "user.email", "t@example.test")
    _git(origin, "config", "user.name", "t")
    skill = origin / "bob" / ".grok" / "skills" / "harvest"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("lesson-A\n", encoding="utf-8")
    common = origin / "common" / ".grok" / "skills" / "harvest-agent-skills"
    common.mkdir(parents=True)
    (common / "SKILL.md").write_text("harvest-A\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "skills A")
    install = tmp_path / "install"
    subprocess.run(
        ["git", "clone", str(origin), str(install)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(install, "config", "user.email", "t@example.test")
    _git(install, "config", "user.name", "t")
    return origin, install


def test_fr7238_dirty_install_overlays_skills(tmp_path: Path) -> None:
    origin, install = _init_pair(tmp_path)
    (install / "hotpatch.py").write_text("dirty\n", encoding="utf-8")
    harvest = install / "bob" / ".grok" / "skills" / "harvest" / "SKILL.md"
    harvest.write_text("stale-local\n", encoding="utf-8")
    (install / "worker").mkdir()
    skill = origin / "bob" / ".grok" / "skills" / "harvest" / "SKILL.md"
    skill.write_text("lesson-B\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "skills B")
    got = sis.sync_install_skills_from_origin(install, fetch=True, job_busy=False)
    assert got["ok"] is True
    assert harvest.read_text(encoding="utf-8") == "lesson-B\n"
    assert (install / "hotpatch.py").read_text(encoding="utf-8") == "dirty\n"
    assert sis.read_skills_sha(install) == got["sha"]
    assert len(got["sha"]) >= 7
    mirrored = install / "worker" / ".grok" / "skills" / "harvest" / "SKILL.md"
    assert mirrored.read_text(encoding="utf-8") == "lesson-B\n"


def test_fr7238_mid_job_skips(tmp_path: Path) -> None:
    origin, install = _init_pair(tmp_path)
    harvest = install / "bob" / ".grok" / "skills" / "harvest" / "SKILL.md"
    harvest.write_text("job-loaded\n", encoding="utf-8")
    (origin / "bob" / ".grok" / "skills" / "harvest" / "SKILL.md").write_text(
        "lesson-C\n", encoding="utf-8"
    )
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "skills C")
    got = sis.sync_install_skills_from_origin(install, job_busy=True)
    assert got["ok"] is False
    assert got["reason"] == "mid-job"
    assert harvest.read_text(encoding="utf-8") == "job-loaded\n"


def test_fr7238_sync_script_calls_overlay() -> None:
    from repo_layout import ROOT

    t = (ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "sync_install_skills" in t
    assert "FR #7238" in t
    worker = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "maybe_sync_install_skills" in worker
    assert worker.index("def maybe_sync_install_skills") < worker.index(
        "skills-sync start"
    )


def test_fr7238_digest_field_wired() -> None:
    assert "skills_sha" in bobreport._MERGE_PEER_FIELDS
    assert "skills_sha" in bobreport._TRAY_MACHINE_EXPORT_KEYS


def test_fr7238_attach_peer_skills_sha(tmp_path: Path) -> None:
    install = tmp_path / "bob"
    (install / "run").mkdir(parents=True)
    (install / "run" / sis.STAMP_NAME).write_text("abcdef1234567890\n", encoding="utf-8")
    peer = bobreport.attach_peer_skills_sha({"id": "flamingo"}, install)
    assert peer.get("skills_sha") == "abcdef1234567890"
    blob = str(peer)
    assert "password" not in blob.lower()
