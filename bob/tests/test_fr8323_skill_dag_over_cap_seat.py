"""FR #8323: an over-cap seat SKILL.md must not hide a later slim book."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp


def _skill(dir_path: Path, name: str, body: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {name} book\ndepends_on: []\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_fr8323_over_cap_seat_yields_to_slim_later_root(tmp_path: Path):
    worker = tmp_path / "worker" / ".grok" / "skills"
    common = tmp_path / "common" / ".grok" / "skills"
    fat = "x" * (idx.SKILL_RESOLVE_CAP_BYTES + 50)
    seat = _skill(worker / "harvest", "harvest", fat)
    slim = _skill(common / "harvest", "harvest", "slim common book")

    nodes, collisions = idx.scan_skills_with_collisions([worker, common])
    assert collisions == []
    node = next(n for n in nodes if n["id"] == "harvest")
    assert Path(node["path"]).resolve() == slim.resolve()
    assert node["bytes"] <= idx.SKILL_RESOLVE_CAP_BYTES
    assert Path(node["path"]).resolve() != seat.resolve()

    server = mcp.SkillDagServer(roots=[worker, common])
    got = server.resolve("harvest")
    assert got["matched"]
    assert got["matched"][0]["path"] == str(slim.resolve())
    assert all(s["id"] != "harvest" or s["reason"] != "over_budget" for s in got["skipped"])


def test_fr8323_under_cap_seat_still_wins(tmp_path: Path):
    worker = tmp_path / "worker" / ".grok" / "skills"
    common = tmp_path / "common" / ".grok" / "skills"
    seat = _skill(worker / "harvest", "harvest", "seat slim")
    _skill(common / "harvest", "harvest", "common slim")
    nodes, _collisions = idx.scan_skills_with_collisions([worker, common])
    node = next(n for n in nodes if n["id"] == "harvest")
    assert Path(node["path"]).resolve() == seat.resolve()
