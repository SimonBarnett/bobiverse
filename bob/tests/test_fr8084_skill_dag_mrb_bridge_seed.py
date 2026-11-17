"""FR #8084: an MRB job kind maps to bobiverse-bob-job-mrb despite a bridge seed."""
from __future__ import annotations

from pathlib import Path

import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
REAL_ROOTS = [
    REPO / "bob" / ".grok" / "skills",
    REPO / "common" / ".grok" / "skills",
    REPO / "worker" / ".grok" / "skills",
]


def _server() -> mcp.SkillDagServer:
    present = [p for p in REAL_ROOTS if p.is_dir()]
    assert present
    return mcp.SkillDagServer(roots=present)


def test_fr8084_mrb_kind_wins_over_bridge_worktree_seed():
    server = _server()
    seeds = (
        "bob-bridge MRB",
        "MRB bob-bridge",
        "worktree bob-bridge task MRB",
        "bob-job-mrb harvest lesson PASS merge keep-both",
    )
    for seed in seeds:
        out = server.resolve(seed)
        ids = [n["id"] for n in out["matched"]]
        assert ids, seed
        assert ids[0] == "bobiverse-bob-job-mrb", (seed, ids[:3])


def test_fr8084_bridge_only_seed_does_not_pick_opencode_setup():
    server = _server()
    out = server.resolve("bob-bridge")
    ids = [n["id"] for n in out["matched"]]
    assert "bob-setup-opencode" not in ids
    assert "bobiverse-bob-job-mrb" not in ids
