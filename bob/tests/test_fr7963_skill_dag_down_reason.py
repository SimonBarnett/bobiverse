"""FR #7963: skill_dag_down GIVEUP carries probe detail; seat fault not job fault."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr7963_giveup_line_includes_probe_reason():
    assert (
        bw.skill_dag_down_giveup_line(
            "FR SimonBarnett/bobiverse#7963", probe_reason="exit-1"
        )
        == "GIVEUP FR SimonBarnett/bobiverse#7963 skill_dag_down:exit-1"
    )


def test_fr7963_giveup_line_includes_skill_basename():
    line = bw.skill_dag_down_giveup_line(
        "FR SimonBarnett/bobiverse#7963",
        probe_reason="bad-json",
        skill_path=r"C:\ai\bob\bob\.grok\skills\bobiverse-bob-job-fr\SKILL.md",
    )
    assert line == (
        "GIVEUP FR SimonBarnett/bobiverse#7963 skill_dag_down:bad-json:skill=SKILL.md"
    )


def test_fr7963_giveup_line_bare_when_no_detail():
    assert (
        bw.skill_dag_down_giveup_line("FR SimonBarnett/bobiverse#7963")
        == "GIVEUP FR SimonBarnett/bobiverse#7963 skill_dag_down"
    )


def test_fr7963_detail_token_strips_spaces():
    assert (
        bw.skill_dag_down_detail_token("run TimeoutExpired")
        == "skill_dag_down:run-TimeoutExpired"
    )


def test_fr7963_skill_dag_mcp_script_path_uses_shipped_resolver(tmp_path: Path, monkeypatch):
    """Frozen/shipped path wins so stale C:\\ai\\bob checkout is not preferred (FR #7963)."""
    cwd = tmp_path / "worker"
    cwd.mkdir()
    stale = tmp_path / "bob" / "scripts" / "skill_dag_mcp.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("# stale\n", encoding="utf-8")
    shipped = tmp_path / "shipped" / "skill_dag_mcp.py"
    shipped.parent.mkdir(parents=True)
    shipped.write_text("# shipped\n", encoding="utf-8")

    def fake_resolve(name, **kwargs):
        assert name == "skill_dag_mcp.py"
        return shipped

    monkeypatch.setattr(bw, "_resolve_installed_worker_script", fake_resolve)
    got = bw.skill_dag_mcp_script_path(str(cwd))
    assert got == shipped.resolve()


def test_fr7963_worker_shipped_scripts_lists_skill_dag_mcp():
    names = __import__("worker_shipped_scripts").by_path_script_names(
        Path(bw.__file__).read_text(encoding="utf-8")
    )
    assert "skill_dag_mcp.py" in names
