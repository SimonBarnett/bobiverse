"""FR #6889: skill-dag MCP script path must exist on a repo-shaped tree."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _repo_shaped(tmp_path: Path) -> tuple[Path, Path]:
    """Bobiverse checkout: bob/scripts/skill_dag_mcp.py + worker/ cwd."""
    script = tmp_path / "bob" / "scripts" / "skill_dag_mcp.py"
    script.parent.mkdir(parents=True)
    script.write_text("# skill-dag mcp stub\n", encoding="utf-8")
    worker = tmp_path / "worker"
    worker.mkdir()
    # Wrong legacy location must not win when absent.
    assert not (tmp_path / "common" / "scripts" / "skill_dag_mcp.py").is_file()
    return worker, script


def test_fr6889_script_path_is_file_on_repo_shaped_tree(tmp_path):
    worker, script = _repo_shaped(tmp_path)
    resolved = bw.skill_dag_mcp_script_path(str(worker))
    assert resolved.is_file(), resolved
    assert resolved.resolve() == script.resolve()


def test_fr6889_written_configs_point_at_existing_script(tmp_path):
    worker, script = _repo_shaped(tmp_path)
    want = script.resolve().as_posix()

    grok_cfg = bw.write_skill_dag_mcp_config(str(worker))
    body = grok_cfg.read_text(encoding="utf-8")
    assert want in body.replace("\\", "/")
    assert "common/scripts/skill_dag_mcp.py" not in body.replace("\\", "/")

    doc = bw.cursor_skill_dag_mcp_document(str(worker))
    args = doc["mcpServers"]["skill-dag"]["args"]
    # FR #6922: #6899 added --root packs after the script; this pin is path-exists only.
    assert args, args
    assert Path(args[0]).resolve() == script.resolve()
    assert Path(args[0]).is_file()
