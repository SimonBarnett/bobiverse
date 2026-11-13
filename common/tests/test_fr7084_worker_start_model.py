"""FR #7084: per-CLI start models, digest mismatch, Jeeves cheapest qualifying offer."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import worker_start_model as wsm


CFG = {
    "workerStartModels": {
        "grok": "EXAMPLE_GROK_MIN",
        "cursor": "EXAMPLE_CURSOR_MIN",
        "aider": "EXAMPLE_AIDER_MIN",
        "opencode": "EXAMPLE_OPENCODE_MIN",
    },
    "workerModelCostTiers": {
        "EXAMPLE_GROK_MIN": "min",
        "EXAMPLE_CURSOR_MIN": "min",
        "EXAMPLE_AIDER_MIN": "min",
        "EXAMPLE_OPENCODE_MIN": "min",
        "EXAMPLE_GROK_MAX": "max",
    },
    "jobRequiredModelTier": {"FR": "min", "MRB": "medium", "UAT": "max"},
}


def test_fr7084_config_parse_per_cli(tmp_path: Path):
    p = tmp_path / "models.json"
    p.write_text(
        '{"workerStartModels": {"grok": "EXAMPLE_GROK_MIN", "cursor": "EXAMPLE_CURSOR_MIN"}}',
        encoding="utf-8",
    )
    cfg = wsm.load_worker_start_config(path=p)
    assert cfg["workerStartModels"]["grok"] == "EXAMPLE_GROK_MIN"
    assert cfg["workerStartModels"]["cursor"] == "EXAMPLE_CURSOR_MIN"
    assert cfg["workerStartModels"]["aider"] == ""
    assert cfg["workerStartModels"]["opencode"] == ""


def test_fr7084_config_does_not_invent_ids():
    cfg = wsm.load_worker_start_config({})
    for cli in wsm.WORKER_CLIS:
        assert cfg["workerStartModels"][cli] == ""


def test_fr7084_launch_argv_includes_configured_model():
    for kind in ("grok", "cursor", "aider", "opencode"):
        model = CFG["workerStartModels"][kind]
        argv = wsm.launch_argv_with_model(kind, [f"{kind}.exe", "--cwd", "x"], model)
        assert "--model" in argv
        assert argv[argv.index("--model") + 1] == model


def test_fr7084_empty_model_does_not_add_flag():
    argv = wsm.launch_argv_with_model("grok", ["grok.exe", "-s", "sid"], "")
    assert "--model" not in argv


def test_fr7084_mismatch_detection():
    assert wsm.model_mismatch("EXAMPLE_GROK_MAX", "EXAMPLE_GROK_MIN") is True
    assert wsm.model_mismatch("EXAMPLE_GROK_MIN", "EXAMPLE_GROK_MIN") is False
    assert wsm.model_mismatch("", "") is False


def test_fr7084_digest_fields_for_seat_states():
    for state in ("held", "starting", "idle", "busy"):
        fields = wsm.digest_seat_model_fields(
            cli="grok", actual="EXAMPLE_GROK_MIN", cfg=CFG, state=state
        )
        assert fields["start_model"] == "EXAMPLE_GROK_MIN"
        assert fields["configured_model"] == "EXAMPLE_GROK_MIN"
        assert fields["model_mismatch"] is False
        assert fields["state"] == state
        assert "cost_tier" in fields


def test_fr7084_digest_mismatch_flag():
    fields = wsm.digest_seat_model_fields(
        cli="grok", actual="EXAMPLE_GROK_MAX", cfg=CFG, state="idle"
    )
    assert fields["model_mismatch"] is True


def test_fr7084_post_digest_includes_mismatch(monkeypatch):
    captured = {}

    def _fake_post(url, payload, log=None):
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    ok = bw.post_digest_seat_kind(
        machine="flamingo",
        pid=99,
        nick="flamingo-99",
        kind="grok",
        model="EXAMPLE_GROK_MAX",
        configured_model="EXAMPLE_GROK_MIN",
        model_mismatch=True,
        cost_tier="max",
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    body = captured["payload"]
    assert body["model"] == "EXAMPLE_GROK_MAX"
    assert body["start_model"] == "EXAMPLE_GROK_MAX"
    assert body["configured_model"] == "EXAMPLE_GROK_MIN"
    assert body["model_mismatch"] is True
    assert body["cost_tier"] == "max"


def test_fr7084_coerce_worker_keeps_model_fields():
    import bobreport

    w = bobreport._coerce_worker(
        "flamingo",
        "99",
        {
            "kind": "grok",
            "state": "idle",
            "start_model": "EXAMPLE_GROK_MIN",
            "configured_model": "EXAMPLE_GROK_MIN",
            "model_mismatch": False,
            "cost_tier": "min",
        },
    )
    assert w["start_model"] == "EXAMPLE_GROK_MIN"
    assert w["configured_model"] == "EXAMPLE_GROK_MIN"
    assert w["model_mismatch"] is False
    assert w["cost_tier"] == "min"


def test_fr7084_worker_list_keeps_model_fields_all_states():
    import bobreport

    raw = [
        {
            "nick": f"flamingo-{i}",
            "state": state,
            "start_model": "EXAMPLE_GROK_MIN",
            "configured_model": "EXAMPLE_GROK_MIN",
            "model_mismatch": False,
            "cost_tier": "min",
            "kind": "grok",
        }
        for i, state in enumerate(("idle", "offered", "doing"), start=1)
    ]
    rows = bobreport._coerce_worker_list(raw)
    assert len(rows) == 3
    for row in rows:
        assert row["start_model"] == "EXAMPLE_GROK_MIN"
        assert row["model_mismatch"] is False


def test_fr7084_tier_match_and_cheapest_and_mismatch_skip():
    seats = [
        {
            "nick": "a-1",
            "start_model": "EXAMPLE_GROK_MAX",
            "cost_tier": "max",
            "model_mismatch": False,
        },
        {
            "nick": "b-2",
            "start_model": "EXAMPLE_GROK_MIN",
            "cost_tier": "min",
            "model_mismatch": False,
        },
        {
            "nick": "c-3",
            "start_model": "EXAMPLE_GROK_MIN",
            "cost_tier": "min",
            "model_mismatch": True,
        },
    ]
    fr = wsm.pick_cheapest_qualifying_seats(seats, "FR", CFG)
    assert [s["nick"] for s in fr] == ["b-2", "a-1"]
    mrb = wsm.pick_cheapest_qualifying_seats(seats, "MRB", CFG)
    assert [s["nick"] for s in mrb] == ["a-1"]
    uat = wsm.pick_cheapest_qualifying_seats(seats, "UAT", CFG)
    assert [s["nick"] for s in uat] == ["a-1"]


def test_fr7084_no_qualifying_seat_stays_queued():
    seats = [{"nick": "x-1", "cost_tier": "min", "model_mismatch": False}]
    assert wsm.pick_cheapest_qualifying_seats(seats, "UAT", CFG) == []


def test_fr7084_grok_launch_uses_configured_model():
    argv = ["grok.exe", "--no-auto-update", "-s", "sid"]
    got = wsm.launch_argv_with_model("grok", argv, "EXAMPLE_GROK_MIN")
    assert got[0] == "grok.exe"
    assert got[1:3] == ["--model", "EXAMPLE_GROK_MIN"]
