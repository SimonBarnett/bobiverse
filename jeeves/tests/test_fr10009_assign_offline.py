"""FR #10009: assign and requeue trust stamps, not live GitHub."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_fr10009_stamped_closed_skips_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dial")),
    )
    doc = {
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9",
                "state": "closed",
            }
        ]
    }
    why = gitclaim.closed_unmerged_ref_skip_reason(doc, "SimonBarnett/bobiverse", "9")
    assert why and "closed" in why
    src = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "pr_exists=None" in src
    assert "github_pr_exists_checker" not in src.split("def _assign_row_named")[1].split("def _finish_assign_result")[0]
