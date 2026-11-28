"""FR #8059: seat opencode.json must not point at a job-worktree script."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import worker_shipped_scripts as shipped


def _script(folder: Path, name: str = "skill_dag_mcp.py") -> Path:
    path = folder / "bob" / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# %s\n" % name, encoding="utf-8")
    return path


def test_fr8059_writer_uses_install_script_not_job_worktree(tmp_path, monkeypatch):
    install = tmp_path / "install"
    (install / ".git").mkdir(parents=True)
    stable = _script(install)
    _script(install, "skill_dag_index.py")
    worker = install / "worker"
    worker.mkdir()
    job = tmp_path / "worktrees" / "bobiverse" / "fr-8008"
    job.mkdir(parents=True)
    (job / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    job_script = _script(job)
    monkeypatch.setattr(bw, "__file__", str(job / "bob" / "scripts" / "bob_worker.py"))
    cfg = bw.write_opencode_skill_dag_mcp_config(worker, worker_cwd=str(worker))
    doc = json.loads(cfg.read_text(encoding="utf-8"))
    entry = doc["mcp"]["skill-dag"]
    assert entry["url"] == bw.BOB_SKILL_MCP_URL
    body = cfg.read_text(encoding="utf-8")
    assert "fr-8008" not in body
    assert "skill_dag_mcp.py" not in body
    assert "worktrees" not in body.lower()
    assert stable.is_file()


def test_fr8059_script_path_skips_linked_worktree_even_without_install_file(tmp_path, monkeypatch):
    install = tmp_path / "install"
    (install / ".git").mkdir(parents=True)
    worker = install / "worker"
    worker.mkdir()
    job = tmp_path / "worktrees" / "bobiverse" / "fr-8008"
    job.mkdir(parents=True)
    (job / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    _script(job)
    monkeypatch.setattr(bw, "__file__", str(job / "bob" / "scripts" / "bob_worker.py"))
    resolved = bw.skill_dag_mcp_script_path(str(worker))
    text = resolved.as_posix().lower()
    assert "worktrees" not in text
    assert "fr-8008" not in text


def test_fr8059_by_path_shipping_still_lists_skill_dag_mcp():
    """MRB #8075: keep _resolve_installed_worker_script so FR #7910 ships the MCP."""
    text = Path(bw.__file__).read_text(encoding="utf-8")
    names = shipped.by_path_script_names(text)
    assert "skill_dag_mcp.py" in names
