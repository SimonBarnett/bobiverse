"""FR #8064: opencode.json allows fleet script reads and denies C:\\passwords."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def test_fr8064_generated_config_allows_fleet_scripts_and_denies_passwords(tmp_path: Path):
    install = tmp_path / "ai" / "bob"
    worker = install / "worker"
    worker.mkdir(parents=True)
    for rel in ("bob/scripts", "common/scripts"):
        (install / rel).mkdir(parents=True)
    (install / "common" / "scripts" / "Add-BobiverseOutboxLine.ps1").write_text(
        "# outbox\n", encoding="utf-8"
    )
    job = tmp_path / "worktree"
    cfg = bw.write_opencode_skill_dag_mcp_config(job, worker_cwd=str(worker))
    # A later rewrite must keep the same allows (FR #8059 class of drop).
    cfg = bw.write_opencode_skill_dag_mcp_config(job, worker_cwd=str(worker))
    data = json.loads(cfg.read_text(encoding="utf-8"))
    allow = data["permission"]["external_directory"]
    edit = data["permission"]["edit"]
    common = (install / "common" / "scripts").resolve()
    bob_scripts = (install / "bob" / "scripts").resolve()
    asked = str(common) + "\\*"
    assert allow.get(asked) == "allow"
    assert allow.get(str(bob_scripts) + "\\*") == "allow"
    assert edit.get(asked) == "deny"
    assert allow.get(r"C:\passwords") == "deny"
    assert allow.get(r"C:\passwords\*") == "deny"
    assert "passwords" not in asked.lower()
    joined = " ".join(k for k, v in allow.items() if v == "allow").lower()
    assert "\\passwords" not in joined
    assert "/passwords" not in joined
