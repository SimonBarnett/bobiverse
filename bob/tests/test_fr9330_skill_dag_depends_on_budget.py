"""FR #9330: resolve keeps depends_on (job-irc) when the seed body is large."""
from __future__ import annotations

import json
from pathlib import Path

import skill_dag_mcp as mcp


def _write_skill(
    root: Path,
    name: str,
    description: str,
    body_bytes: int,
    depends_on: list[str] | None = None,
) -> None:
    deps = depends_on or []
    if deps:
        dep_block = "depends_on:\n" + "".join(f"  - {d}\n" for d in deps)
    else:
        dep_block = "depends_on: []\n"
    text = (
        f"---\nname: {name}\ndescription: {description}\n{dep_block}---\n\n"
        + ("B" * body_bytes)
    )
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")


def test_fr9330_mrb_seed_keeps_direct_depends_on_under_default_cap(tmp_path: Path):
    """MRB-sized seed must not crowd out job-irc / harvest under DEFAULT_MAX_BYTES.

    Reproduces intake evidence: matched=[mrb] skipped=[harvest, irc] over_budget
    when resolve charged full body sizes for metadata-only matches.
    """
    root = tmp_path / "skills"
    root.mkdir()
    # Sizes mirror production worker skills (approx).
    _write_skill(root, "harvest", "honesty box harvest playbook", 42000, [])
    _write_skill(
        root,
        "bobiverse-bob-job-irc",
        "Exact IRC wire contract ACK DONE NACK GIVEUP",
        17000,
        ["harvest"],
    )
    _write_skill(
        root,
        "bobiverse-bob-job-mrb",
        "The single skill for MRB jobs hostile review",
        59000,
        ["bobiverse-bob-job-irc"],
    )
    server = mcp.SkillDagServer(roots=[root], max_bytes=mcp.DEFAULT_MAX_BYTES)
    out = server.resolve("MRB SimonBarnett/bobiverse#9305")
    ids = [n["id"] for n in out["matched"]]
    skipped = {s["id"]: s["reason"] for s in out.get("skipped") or []}
    assert "bobiverse-bob-job-mrb" in ids, out
    assert "bobiverse-bob-job-irc" in ids, (
        f"direct depends_on dropped: matched={ids} skipped={skipped}"
    )
    assert "harvest" in ids, f"transitive depends_on dropped: matched={ids} skipped={skipped}"
    assert "bobiverse-bob-job-irc" not in skipped
    blob = json.dumps(out, ensure_ascii=False)
    assert len(blob.encode("utf-8")) <= server.max_bytes


def test_fr9330_single_body_over_cap_still_skipped(tmp_path: Path):
    """S4: a single body larger than max_bytes remains over_budget at resolve."""
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "fat-skill", "oversized body alone", 8000, [])
    server = mcp.SkillDagServer(roots=[root], max_bytes=4000)
    out = server.resolve("fat-skill")
    skipped_ids = [s["id"] for s in out.get("skipped") or []]
    assert "fat-skill" in skipped_ids
    assert out["matched"] == []
    blob = json.dumps(out, ensure_ascii=False)
    assert len(blob.encode("utf-8")) <= server.max_bytes


def test_fr9330_seed_still_preferred_when_meta_budget_tight(tmp_path: Path):
    """FR #6890 carve-out: seed stays matched when only metadata room for one row."""
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "dep-a", "dependency a", 100, [])
    _write_skill(
        root,
        "bobiverse-bob-job-fr",
        "The single skill for FR jobs",
        100,
        ["dep-a"],
    )
    # Tiny cap: one metadata row fits, not two.
    server = mcp.SkillDagServer(roots=[root], max_bytes=400)
    out = server.resolve("FR")
    ids = [n["id"] for n in out["matched"]]
    assert "bobiverse-bob-job-fr" in ids
    assert "dep-a" not in ids