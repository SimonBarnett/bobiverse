"""FR #8225: resolve must not silently return empty for FR/MRB job seeds."""
from __future__ import annotations

from pathlib import Path

from skill_dag_mcp import JOB_SEEDS, SkillDagServer


def _write_skill(root: Path, skill_id: str, description: str, *, depends_on: str = "[]") -> Path:
    d = root / skill_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "SKILL.md"
    path.write_text(
        f"---\nname: {skill_id}\ndescription: {description}\ndepends_on: {depends_on}\n---\n\n# {skill_id}\n",
        encoding="utf-8",
    )
    return path


def test_fr8225_job_seed_missing_from_index_is_not_silent_empty(tmp_path: Path):
    """Hostile (redqueen-7968): JOB_SEEDS maps FR but skill not indexed → not_in_index."""
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "skill-dag-core", "Process-local skill catalog is the core stub only")
    server = SkillDagServer(roots=[root], max_bytes=65536)
    assert "bobiverse-bob-job-fr" not in server.nodes
    assert JOB_SEEDS["FR"] == "bobiverse-bob-job-fr"
    out = server.resolve(
        "FR SimonBarnett/bobiverse#8221 https://github.com/SimonBarnett/bobiverse/issues/8221"
    )
    assert out.get("matched") == []
    assert out.get("unresolved") is True
    assert out.get("reason") == "not_in_index"
    assert out.get("seed_id") == "bobiverse-bob-job-fr"
    skipped = out.get("skipped") or []
    assert any(
        s.get("id") == "bobiverse-bob-job-fr" and s.get("reason") == "not_in_index" for s in skipped
    )


def test_fr8225_mrb_seed_missing_from_index_reports_not_in_index(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "skill-dag-core", "core stub")
    server = SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("MRB SimonBarnett/bobiverse#8224 https://github.com/x/pull/1")
    assert out.get("matched") == []
    assert out.get("unresolved") is True
    assert out.get("reason") == "not_in_index"
    assert out.get("seed_id") == "bobiverse-bob-job-mrb"


def test_fr8225_full_index_fr_seed_still_matches(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "skill-dag-core", "core stub")
    _write_skill(
        root,
        "bobiverse-bob-job-irc",
        "Exact IRC wire contract for worker jobs",
        depends_on='["harvest"]',
    )
    _write_skill(
        root,
        "bobiverse-bob-job-fr",
        "The single skill for FR jobs",
        depends_on='["bobiverse-bob-job-irc"]',
    )
    _write_skill(root, "harvest", "Harvest intake")
    server = SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("FR SimonBarnett/bobiverse#8225")
    ids = [m["id"] for m in out.get("matched") or []]
    assert "bobiverse-bob-job-fr" in ids
    assert out.get("unresolved") is not True


def test_fr8225_no_seed_match_is_explicit(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "skill-dag-core", "core stub only")
    server = SkillDagServer(roots=[root], max_bytes=65536)
    out = server.resolve("zzzz-no-overlap-token-xyzzy")
    assert out.get("matched") == []
    assert out.get("unresolved") is True
    assert out.get("reason") == "no_seed_match"
