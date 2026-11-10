"""FR #6387: measured model + token stamps on DONE; durable per-PR cost ledger."""
from __future__ import annotations

import json
from pathlib import Path

import done_usage
import job_cost_ledger
import shop_listen


def test_parse_done_usage_new_fields():
    rest = (
        "PASS https://github.com/o/r/pull/1 "
        "model=xai/grok-4.5 tokens_in=100 tokens_out=20 tokens_cached=50"
    )
    u = done_usage.parse_done_usage(rest)
    assert u["model"] == "xai/grok-4.5"
    assert u["tokens_in"] == 100
    assert u["tokens_out"] == 20
    assert u["tokens_cached"] == 50
    assert u["tokens_unknown"] is False
    assert u["legacy_tokens"] is None


def test_parse_done_usage_legacy_tokens():
    rest = "PASS https://github.com/o/r/pull/2 tokens=1200 review=light"
    u = done_usage.parse_done_usage(rest)
    assert u["legacy_tokens"] == 1200
    assert u["tokens_unknown"] is False
    assert u["tokens_in"] is None


def test_parse_done_usage_tokens_unknown():
    rest = "PASS https://github.com/o/r/pull/3 tokens=unknown"
    u = done_usage.parse_done_usage(rest)
    assert u["tokens_unknown"] is True
    assert u["legacy_tokens"] is None
    assert u["tokens_in"] is None


def test_parse_done_usage_none_is_unknown_not_zero():
    rest = "PASS https://github.com/o/r/pull/4"
    u = done_usage.parse_done_usage(rest)
    assert u["tokens_unknown"] is True
    assert u["legacy_tokens"] is None
    assert u["tokens_in"] is None
    assert u["tokens_out"] is None
    assert u.get("tokens_total") is None


def test_format_suffix_measured():
    s = done_usage.format_done_usage_suffix(
        {
            "model": "xai/grok-4.5",
            "tokens_in": 10,
            "tokens_out": 2,
            "tokens_cached": 5,
        }
    )
    assert s == "model=xai/grok-4.5 tokens_in=10 tokens_out=2 tokens_cached=5 worker_build=unknown"


def test_format_suffix_unknown():
    assert done_usage.format_done_usage_suffix({}) == "tokens=unknown worker_build=unknown"
    assert (
        done_usage.format_done_usage_suffix({"tokens_unknown": True, "model": "x"})
        == "model=x tokens=unknown worker_build=unknown"
    )


def test_enrich_done_appends_measured_and_overrides_model_tokens():
    bare = "DONE FR o/r#1 https://github.com/o/r/pull/9"
    measured = {
        "model": "xai/grok-4.5",
        "tokens_in": 11,
        "tokens_out": 3,
        "tokens_cached": 7,
    }
    out = done_usage.enrich_done_payload(bare, measured)
    assert out.startswith(bare)
    assert "model=xai/grok-4.5" in out
    assert "tokens_in=11" in out
    assert "tokens_out=3" in out
    assert "tokens_cached=7" in out

    with_model = (
        "DONE MRB o/r#2 PASS https://github.com/o/r/pull/8 tokens=999 model=fake"
    )
    out2 = done_usage.enrich_done_payload(with_model, measured)
    assert "tokens=999" not in out2
    assert "model=fake" not in out2
    assert "tokens_in=11" in out2
    assert out2.count("model=") == 1


def test_enrich_non_done_unchanged():
    line = "ACK FR o/r#1"
    assert done_usage.enrich_done_payload(line, {"tokens_in": 1}) == line


def test_read_grok_usage_json(tmp_path: Path):
    usage = {
        "sessionId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "session": {
            "inputTokens": 1000,
            "outputTokens": 40,
            "cachedReadTokens": 800,
            "primaryModelId": "grok-4.5-build",
        },
    }
    path = tmp_path / "usage.json"
    path.write_text(json.dumps(usage), encoding="utf-8")
    u = done_usage.read_grok_usage(path)
    assert u["model"] == "xai/grok-4.5-build"
    assert u["tokens_in"] == 1000
    assert u["tokens_out"] == 40
    assert u["tokens_cached"] == 800
    assert u["tokens_unknown"] is False


def test_read_cursor_usage_fixture(tmp_path: Path):
    doc = {
        "model": "cursor/composer-1",
        "usage": {
            "input_tokens": 500,
            "output_tokens": 25,
            "cache_read_tokens": 100,
        },
    }
    path = tmp_path / "cursor-usage.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    u = done_usage.read_cursor_usage(path)
    assert u["model"] == "cursor/composer-1"
    assert u["tokens_in"] == 500
    assert u["tokens_out"] == 25
    assert u["tokens_cached"] == 100


def test_read_opencode_usage_fixture(tmp_path: Path):
    doc = {
        "model": "opencode/glm-5.3",
        "tokens": {"input": 200, "output": 15, "cache": 50},
    }
    path = tmp_path / "opencode-session.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    u = done_usage.read_opencode_usage(path)
    assert u["model"] == "opencode/glm-5.3"
    assert u["tokens_in"] == 200
    assert u["tokens_out"] == 15
    assert u["tokens_cached"] == 50


def test_read_aider_usage_fixture(tmp_path: Path):
    doc = {
        "model": "aider/deepseek-chat",
        "prompt_tokens": 300,
        "completion_tokens": 12,
        "cached_tokens": 0,
    }
    path = tmp_path / "aider-usage.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    u = done_usage.read_aider_usage(path)
    assert u["model"] == "aider/deepseek-chat"
    assert u["tokens_in"] == 300
    assert u["tokens_out"] == 12
    assert u["tokens_cached"] == 0


def test_measure_seat_usage_dispatches(tmp_path: Path):
    grok = tmp_path / "g" / "usage.json"
    grok.parent.mkdir()
    grok.write_text(
        json.dumps(
            {
                "session": {
                    "inputTokens": 9,
                    "outputTokens": 1,
                    "cachedReadTokens": 2,
                    "primaryModelId": "grok-4.5",
                }
            }
        ),
        encoding="utf-8",
    )
    u = done_usage.measure_seat_usage("grok", grok_usage_path=grok)
    assert u["tokens_in"] == 9
    assert u["model"].endswith("grok-4.5")

    missing = done_usage.measure_seat_usage("grok", grok_usage_path=tmp_path / "nope.json")
    assert missing["tokens_unknown"] is True


def test_shop_listen_meta_includes_new_fields():
    parsed = shop_listen.parse_shop_job_line(
        "DONE FR SimonBarnett/bobiverse#6387 "
        "https://github.com/SimonBarnett/bobiverse/pull/6400 "
        "model=xai/grok-4.5 tokens_in=10 tokens_out=2 tokens_cached=4"
    )
    assert parsed is not None
    meta = shop_listen.done_usage_meta(parsed.rest)
    assert meta["model"] == "xai/grok-4.5"
    assert meta["tokens_in"] == 10
    assert meta["tokens_out"] == 2
    assert meta["tokens_cached"] == 4


def test_shop_listen_tokens_unknown_and_none():
    p1 = shop_listen.parse_shop_job_line(
        "DONE MRB o/r#1 PASS https://github.com/o/r/pull/1 tokens=unknown"
    )
    assert shop_listen.done_usage_meta(p1.rest)["tokens_unknown"] is True

    p2 = shop_listen.parse_shop_job_line(
        "DONE FIX o/r#2 https://github.com/o/r/pull/2"
    )
    meta = shop_listen.done_usage_meta(p2.rest)
    assert meta["tokens_unknown"] is True
    assert meta.get("legacy_tokens") is None


def test_ledger_sums_fr_mrb_fix_for_one_pr(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#9",
        task="FR",
        seat="redqueen-1",
        rest="https://github.com/o/r/pull/9 model=xai/a tokens_in=100 tokens_out=10 tokens_cached=20",
    )
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#9",
        task="MRB",
        seat="flamingo-1",
        rest="PASS https://github.com/o/r/pull/9 model=xai/b tokens_in=50 tokens_out=5 tokens_cached=10",
    )
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#9",
        task="FIX",
        seat="redqueen-2",
        rest="https://github.com/o/r/pull/9 model=cursor/c tokens_in=25 tokens_out=2 tokens_cached=0",
    )
    # unknown must not add a fabricated 0 into totals
    job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#9",
        task="UAT",
        seat="ionos-1",
        rest="PASS https://github.com/o/r/pull/9 tokens=unknown",
    )
    totals = job_cost_ledger.per_pr_totals(home, "o/r#9")
    assert totals["jobs"] == 4
    assert totals["tokens_in"] == 175
    assert totals["tokens_out"] == 17
    assert totals["tokens_cached"] == 30
    assert totals["measured_jobs"] == 3
    assert totals["unknown_jobs"] == 1
    models = totals["models"]
    assert "xai/a" in models
    assert "xai/b" in models
    assert "cursor/c" in models


def test_ledger_none_stored_as_unknown_not_zero(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    row = job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#3",
        task="FR",
        seat="s",
        rest="https://github.com/o/r/pull/3",
    )
    assert row["tokens_unknown"] is True
    assert row["tokens_in"] is None
    assert row["tokens_out"] is None
    assert row.get("legacy_tokens") is None
    # summarize must not treat unknown as 0 contribution
    tot = job_cost_ledger.per_pr_totals(home, "o/r#3")
    assert tot["tokens_in"] == 0
    assert tot["unknown_jobs"] == 1
    assert tot["measured_jobs"] == 0


def test_shop_listen_records_ledger_for_fr(tmp_path: Path, monkeypatch):
    """DONE FR path must write the cost ledger (not MRB-only)."""
    import bobreport
    import registered_machines

    home = tmp_path
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    (home / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "shop_listen.complete_job_by_ref",
        lambda *a, **k: ("ok", {"task": "FR", "repo": "o/r", "id": "#7"}),
    )
    monkeypatch.setattr("shop_listen.gitclaim.ledger_note_event", lambda *a, **k: None)
    out = shop_listen.handle_shop_worker_line(
        home,
        nick="redqueen-12345",
        channel="#redqueen",
        body=(
            "DONE FR o/r#7 https://github.com/o/r/pull/7 "
            "model=xai/grok-4.5 tokens_in=3 tokens_out=1 tokens_cached=0"
        ),
        kind="grok",
        post_fn=lambda _p: 204,
    )
    assert out.get("handled") is True
    assert out.get("status") == "ok"
    rows = job_cost_ledger.load_rows(home)
    assert len(rows) == 1
    assert rows[0]["task"] == "FR"
    assert rows[0]["tokens_in"] == 3
    assert rows[0]["pr"] == "o/r#7"
