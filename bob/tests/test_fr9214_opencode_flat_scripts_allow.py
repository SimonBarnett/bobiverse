"""FR #9214: OpenCode allowlist flat install\\scripts; prefer common intake path."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def _fake_install(tmp_path: Path, *, with_flat: bool = True, with_common: bool = True) -> Path:
    install = tmp_path / "ai" / "bob"
    worker = install / "worker"
    worker.mkdir(parents=True)
    for rel in ("bob/scripts", "common/scripts", "scripts"):
        (install / rel).mkdir(parents=True)
    body = "# intake\n"
    if with_common:
        (install / "common" / "scripts" / "Report-BobiverseIntakeIssue.ps1").write_text(
            body, encoding="utf-8"
        )
    if with_flat:
        (install / "scripts" / "Report-BobiverseIntakeIssue.ps1").write_text(
            body, encoding="utf-8"
        )
    return worker


def test_fr9214_fleet_roots_include_flat_scripts(tmp_path: Path):
    worker = _fake_install(tmp_path)
    install = worker.parent
    roots = bw.opencode_fleet_script_roots(str(worker))
    assert install / "bob" / "scripts" in roots
    assert install / "common" / "scripts" in roots
    assert install / "scripts" in roots


def test_fr9214_generated_config_allows_flat_scripts(tmp_path: Path):
    worker = _fake_install(tmp_path)
    install = worker.parent
    job = tmp_path / "worktree"
    cfg = bw.write_opencode_skill_dag_mcp_config(job, worker_cwd=str(worker))
    # Later rewrite must keep flat + bob + common (FR #8064 / #9214).
    cfg = bw.write_opencode_skill_dag_mcp_config(job, worker_cwd=str(worker))
    data = json.loads(cfg.read_text(encoding="utf-8"))
    allow = data["permission"]["external_directory"]
    edit = data["permission"]["edit"]
    flat = (install / "scripts").resolve()
    asked = str(flat) + "\\*"
    assert allow.get(asked) == "allow"
    assert edit.get(asked) == "deny"
    assert allow.get(r"C:\passwords") == "deny"
    assert allow.get(r"C:\passwords\*") == "deny"


def test_fr9214_resolve_intake_prefers_common_over_flat(tmp_path: Path):
    worker = _fake_install(tmp_path, with_flat=True, with_common=True)
    got = bw.resolve_bobiverse_intake_script(str(worker))
    assert got == (
        worker.parent / "common" / "scripts" / "Report-BobiverseIntakeIssue.ps1"
    ).resolve()


def test_fr9214_resolve_intake_falls_back_to_flat(tmp_path: Path):
    worker = _fake_install(tmp_path, with_flat=True, with_common=False)
    got = bw.resolve_bobiverse_intake_script(str(worker))
    assert got == (
        worker.parent / "scripts" / "Report-BobiverseIntakeIssue.ps1"
    ).resolve()


def test_fr9214_worker_prompt_names_allowed_intake_path(tmp_path: Path, monkeypatch):
    worker = _fake_install(tmp_path, with_flat=True, with_common=True)
    # Force builtin prompt (no tip template) so we pin the resolve path.
    monkeypatch.setattr(bw, "_worker_prompt_from_install_tip", lambda *a, **k: None)
    home = tmp_path / "home"
    home.mkdir()
    prompt = bw.worker_prompt(str(worker), str(home), "marchhare", "marchhare-1")
    common = str(
        (worker.parent / "common" / "scripts" / "Report-BobiverseIntakeIssue.ps1").resolve()
    )
    assert common in prompt
    assert "common\\scripts\\Report-BobiverseIntakeIssue.ps1" in prompt.replace("/", "\\") or common in prompt


def test_fr9214_corrective_names_intake_when_install_scripts_rejected(tmp_path: Path):
    worker = _fake_install(tmp_path)
    intake = bw.resolve_bobiverse_intake_script(str(worker))
    wt = tmp_path / "job"
    wt.mkdir()
    text = bw.opencode_external_dir_corrective_steps(
        job_key="FR SimonBarnett/bobiverse#9214",
        worktree=wt,
        outbox=wt / ".bob" / "outbox.txt",
        scratch=wt / ".bob" / "tmp",
        reject_path=r"C:\ai\bob\scripts\Report-BobiverseIntakeIssue.ps1",
        intake_script=intake,
    )
    assert "CORRECTIVE" in text
    assert str(intake) in text or "Report-BobiverseIntakeIssue.ps1" in text
    assert "common" in text.lower() or "allowed" in text.lower()
