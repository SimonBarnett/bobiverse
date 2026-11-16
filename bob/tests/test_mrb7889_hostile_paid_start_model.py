# -*- coding: utf-8 -*-
"""MRB #7889: hostile pins for FR #7888 paid start_model MRB eligibility."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import gitclaim
import worker_start_model as wsm


ROOT = Path(__file__).resolve().parents[2]


def test_mrb7889_review_class_opencode_go_not_free_via_prefix():
    """opencode-go/* starts with opencode/ but must classify as paid, not free."""
    assert wsm.start_model_review_class("opencode-go/deepseek-v4-pro") == "paid"
    assert wsm.start_model_review_class("opencode/deepseek-v4.1-flash-free") == "free"
    assert wsm.start_model_review_class("$model") == "unknown"
    assert wsm.start_model_review_class("") == "unknown"
    assert wsm.start_model_review_class("grok-4") == "other"


def test_mrb7889_seat_is_free_fuel_ignores_cost_tier_when_paid(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    import bobreport
    import registered_machines

    home = tmp_path
    registered_machines.save_registered(home, {"redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    mid, pid = "redqueen", "8580"
    nick = f"{mid}-{pid}"
    fields = {
        "start_model": "opencode-go/deepseek-v4-pro",
        "configured_model": "opencode/deepseek-v4.1-flash-free",
        "model_mismatch": True,
        "cost_tier": "min",
    }
    doc["machines"][mid] = bobreport._empty_machine(mid)
    worker = {"state": "idle", "nick": nick, "kind": "opencode"}
    worker.update(fields)
    doc["machines"][mid]["workers"] = {pid: worker}
    listed = {
        "nick": nick,
        "state": "idle",
        "work": "",
        "updated": "2026-11-16T12:00:00Z",
        "kind": "opencode",
    }
    listed.update(fields)
    doc["machines"][mid]["worker_list"] = [listed]
    bobreport.save_digest(home, doc)
    assert gitclaim.seat_is_free_fuel(home, nick) is False
    assert "paid start_model" in gitclaim.mrb_eligibility_reason(home, nick)


def test_mrb7889_skills_cite_7888_paid_start_model():
    worker = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #6134 / #7888" in worker
    assert "paid launched" in worker or "paid start_model" in worker.lower()
    # Old unconditional kind=opencode skip must not remain as the live rule.
    assert "refuse when digest `kind=opencode`); still take" not in worker
    setup = (ROOT / "bob" / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #6134 / #7888" in setup
    assert "paid launched" in setup or "paid start_model" in setup.lower()


def test_mrb7889_uat_also_gated_by_start_model():
    line = "FROM jeeves #redqueen redqueen-8580: UAT SimonBarnett/bobiverse#1 https://x"
    assert (
        bw.opencode_skips_hostile_assign(
            "opencode", line, start_model="opencode-go/deepseek-v4-pro"
        )
        is False
    )
    assert (
        bw.opencode_skips_hostile_assign(
            "opencode", line, start_model="opencode/deepseek-v4.1-flash-free"
        )
        is True
    )
