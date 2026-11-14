"""FR #7202: ear CI path filters include every frozen irc_agent common/scripts import."""
from __future__ import annotations

import re
from pathlib import Path

from ear_ci_source_paths import ear_ci_source_paths, frozen_common_script_paths
from repo_layout import ROOT

EAR_WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"


def _on_block(text: str) -> str:
    m = re.search(r"(?ms)^on:\n(.*?)(?=^permissions:|^jobs:)", text)
    assert m, "workflow missing on: block"
    return m.group(1)


def _event_block(on: str, event: str) -> str:
    m = re.search(
        rf"(?ms)^  {re.escape(event)}:\n(.*?)(?=^  [a-z_]+:|\Z)",
        on,
    )
    assert m, f"on: missing {event} block"
    return m.group(1)


def test_frozen_graph_includes_shop_listen_and_chair_health():
    frozen = frozen_common_script_paths()
    assert "common/scripts/irc_agent.py" in frozen
    assert "common/scripts/shop_listen.py" in frozen
    assert "common/scripts/shop_ops.py" in frozen
    assert "common/scripts/chair_health.py" in frozen
    assert "common/scripts/bobstat.py" in frozen
    assert "common/scripts/gitclaim.py" in frozen
    assert "common/scripts/unregister_cmd.py" in frozen


def test_ear_workflow_paths_cover_frozen_common_scripts():
    text = EAR_WF.read_text(encoding="utf-8")
    on = _on_block(text)
    pr_paths = _event_block(on, "pull_request")
    push_paths = _event_block(on, "push")
    want = ear_ci_source_paths()
    assert want, "empty ear CI path list"
    for rel in want:
        assert rel in pr_paths, f"ear pull_request path filter missing {rel}"
        assert rel in push_paths, f"ear push path filter missing {rel}"
    # No extra common/scripts globs that skip the allowlist (would hide missing pins).
    assert "common/scripts/**" not in pr_paths
    assert "common/scripts/*" not in pr_paths.splitlines()
