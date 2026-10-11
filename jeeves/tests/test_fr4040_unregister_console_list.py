"""FR #4040: !unregister dry-run/confirm plan lists mid_console nicks in #mid."""
from __future__ import annotations

from pathlib import Path

import unregister_cmd as uc
from repo_layout import ROOT


def test_fr4040_list_shop_console_nicks():
    members = {
        "#walrus": {
            "walrus_console": {"nick": "walrus_console", "modes": set()},
            "someone": {"nick": "Someone", "modes": {"o"}},
            "other_console": {"nick": "other_console", "modes": set()},
        }
    }
    nicks = uc.list_shop_console_nicks("walrus", members)
    assert nicks == ["other_console", "walrus_console"]
    assert uc.list_shop_console_nicks("walrus", {}) == []
    assert uc.list_shop_console_nicks("walrus", None) == []


def test_fr4040_plan_notes_include_console_list(tmp_path: Path):
    home = tmp_path
    # minimal registered home
    import registered_machines as rm
    rm.save_registered(home, ["ionos"], source=rm.SOURCE_REGISTER)
    members = {
        "#ionos": {
            "ionos_console": {"nick": "ionos_console", "modes": set()},
        }
    }
    plan = uc.build_unregister_plan(
        home,
        {"mid": "ionos", "dry_run": True, "confirm": False},
        asker="simon",
        members=members,
    )
    assert plan is not None
    joined = "\n".join(plan.notes)
    assert "ionos_console" in joined
    assert "console clients:" in joined
    assert "FR #3834" in joined or "wonderland" in joined


def test_fr4040_plan_none_seen(tmp_path: Path):
    import registered_machines as rm
    rm.save_registered(tmp_path, ["ionos"], source=rm.SOURCE_REGISTER)
    plan = uc.build_unregister_plan(
        tmp_path,
        {"mid": "ionos", "dry_run": True, "confirm": False},
        members={"#ionos": {"bob-ionos": {"nick": "bob-ionos", "modes": {"o"}}}},
    )
    assert any("none seen" in n for n in plan.notes)


def test_fr4040_irc_agent_passes_members():
    text = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "members=members" in text
    assert "build_unregister_plan" in text
