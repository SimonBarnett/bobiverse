"""FR #10014: !status github-api line names the paths that spent the bucket."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import github_api_budget as gab  # noqa: E402


def test_fr10014_status_names_paths_and_hour_rolls(tmp_path):
    now = [1_700_000_000.0]
    bud = gab.GithubApiBudget(tmp_path, clock=lambda: now[0], log=lambda _s: None)
    bud.charge("reconcile")
    bud.charge("copilot")
    bud.charge("copilot")
    line = bud.status_line()
    assert "paths=" in line
    assert "copilot=2" in line
    assert "reconcile=1" in line
    now[0] += 3600
    assert bud.status_line().endswith("paths=-") or "paths=-" in bud.status_line()
    assert bud.path_counts == {}
