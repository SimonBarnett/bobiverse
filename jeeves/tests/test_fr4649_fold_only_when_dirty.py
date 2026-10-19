"""FR #4649: never fold origin/main just because a PR is behind."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
AGENTS = ROOT / "bob" / "agents" / "worker" / "AGENTS.md"
LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"

RULE = "never fold just because the PR is behind"
OLD = "at most one update-branch when behind"


def test_mrb_skill_fold_only_when_dirty_or_main_fixed_ci():
    text = MRB.read_text(encoding="utf-8")
    raw = MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert RULE in text
    assert OLD not in text
    assert "CONFLICTING" in text
    assert "DIRTY" in text


def test_worker_agents_and_harvest_log_match_fold_rule():
    agents = AGENTS.read_text(encoding="utf-8")
    log = LOG.read_text(encoding="utf-8")
    assert RULE in agents
    assert OLD not in agents
    assert RULE in log
    assert "Merge origin/main into FR branch before gh pr merge" not in log
