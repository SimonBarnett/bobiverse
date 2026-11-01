"""FR #5865: CodeRabbit-first MRB switch, stamps, gate, sensitive paths, report."""
from __future__ import annotations

from pathlib import Path

import fuel_chain
import gitclaim
import mrb_merge_gate
import mrb_merge_on_green
import shop_listen


def test_wait_default_is_12_minutes(monkeypatch):
    monkeypatch.delenv("BOB_CODERABBIT_WAIT_MIN", raising=False)
    assert fuel_chain.wait_seconds() == 12 * 60


def test_off_stamps_coderabbit_off_and_offers(monkeypatch):
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    row = {"task": "MRB", "repo": "o/r", "id": "#1", "url": "https://github.com/o/r/pull/1"}
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 10.0)
    assert hold is False
    assert row.get("coderabbit") == "off"
    assert row.get("review") == "full"
    line = gitclaim.format_assign_line("n-1", row)
    assert "coderabbit=off" in line
    assert "review=full" in line


def test_absent_when_no_yaml(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: False)
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#2",
        "url": "https://github.com/o/r/pull/2",
        "head_sha": "abc1234",
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 100.0, lookup=lambda *a: False)
    assert hold is False
    assert row.get("coderabbit") == "absent"
    assert row.get("review") == "full"


def test_absent_when_silent_two_minutes(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_state",
        lambda *a, **k: {"ready": False, "failed": False, "activity": False},
    )
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#3",
        "head_sha": "deadbeef",
        "coderabbit_wait_since": 1_000.0,
        "coderabbit_head_sha": "deadbeef",
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 1_000.0 + 121.0)
    assert hold is False
    assert row.get("coderabbit") == "absent"


def test_gate_holds_pending_then_ready_on_head(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_state",
        lambda *a, **k: {"ready": False, "failed": False, "activity": True},
    )
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#4",
        "head_sha": "aaa1111",
        "coderabbit_wait_since": 50.0,
        "coderabbit_head_sha": "aaa1111",
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 60.0, lookup=lambda *a: False)
    assert hold is True
    assert row.get("coderabbit") == "pending"

    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_state",
        lambda *a, **k: {"ready": True, "failed": False, "activity": True},
    )
    hold2 = fuel_chain.apply_mrb_coderabbit_gate(row, 70.0, lookup=lambda *a: True)
    assert hold2 is False
    assert row.get("coderabbit") == "ready"
    assert row.get("review") == "light"


def test_ready_on_old_sha_still_held(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_state",
        lambda *a, **k: {"ready": False, "failed": False, "activity": True},
    )
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#5",
        "head_sha": "newsha01",
        "coderabbit": "ready",
        "coderabbit_wait_since": 10.0,
        "coderabbit_head_sha": "oldsha01",
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 20.0, lookup=lambda *a: False)
    assert hold is True
    assert row.get("coderabbit") == "pending"
    assert row.get("coderabbit_head_sha") == "newsha01"


def test_failed_and_timeout_stamps(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "12")
    monkeypatch.setattr(fuel_chain, "repo_has_coderabbit_yaml", lambda *a, **k: True)
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_state",
        lambda *a, **k: {"ready": False, "failed": True, "activity": True},
    )
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#6",
        "head_sha": "f1",
        "coderabbit_wait_since": 1.0,
        "coderabbit_head_sha": "f1",
    }
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 2.0)
    assert hold is False
    assert row.get("coderabbit") == "failed"
    assert row.get("review") == "full"

    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_state",
        lambda *a, **k: {"ready": False, "failed": False, "activity": True},
    )
    row2 = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#7",
        "head_sha": "t1",
        "coderabbit_wait_since": 100.0,
        "coderabbit_head_sha": "t1",
    }
    hold2 = fuel_chain.apply_mrb_coderabbit_gate(row2, 100.0 + 12 * 60 + 1)
    assert hold2 is False
    assert row2.get("coderabbit") == "timeout"


def test_sensitive_paths_force_full_review():
    files = ["airc/scripts/Install-Airc.ps1", "README.md"]
    assert fuel_chain.sensitive_paths_require_full(files) is True
    assert fuel_chain.sensitive_paths_require_full(["common/tests/test_x.py"]) is False
    assert fuel_chain.review_mode_for("ready", files) == "full"
    assert fuel_chain.review_mode_for("ready", ["bob/scripts/x.py"]) == "light"
    assert fuel_chain.review_mode_for("timeout", ["bob/scripts/x.py"]) == "full"


def test_merge_gate_refuses_pending(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    ok, reason = mrb_merge_gate.evaluate_coderabbit_gate(
        {"coderabbit": "pending", "head_sha": "abc"}
    )
    assert ok is False
    assert "pending" in reason
    ok2, _ = mrb_merge_gate.evaluate_coderabbit_gate({"coderabbit": "ready"})
    assert ok2 is True
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    ok3, _ = mrb_merge_gate.evaluate_coderabbit_gate({"coderabbit": "pending"})
    assert ok3 is True


def test_rollup_ignores_coderabbit_when_nonblocking():
    runs = {
        "check_runs": [
            {"name": "conflict-markers", "status": "completed", "conclusion": "success"},
            {"name": "CodeRabbit", "status": "in_progress", "conclusion": None},
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "pending"
    assert mrb_merge_on_green.rollup_check_runs(runs, ignore_coderabbit=True) == "success"


def test_shop_listen_parses_new_cr_mode_counters():
    parsed = shop_listen.parse_shop_job_line(
        "DONE MRB SimonBarnett/bobiverse#5865 PASS "
        "https://github.com/SimonBarnett/bobiverse/pull/9999 "
        "cr_mode=ready review=light tokens=1200 cr_findings=3 fixed=1 rejected=1 na=1"
    )
    assert parsed is not None
    assert parsed.url.endswith("/pull/9999")
    counters = shop_listen.mrb_cr_counters(parsed.rest)
    assert counters["cr_findings"] == 3
    assert counters["fixed"] == 1
    assert counters["rejected"] == 1
    assert counters["na"] == 1
    meta = shop_listen.mrb_cr_meta(parsed.rest)
    assert meta["cr_mode"] == "ready"
    assert meta["review"] == "light"
    assert meta["tokens"] == 1200


def test_coderabbit_report_row_and_comparison():
    import coderabbit_report

    rows = [
        coderabbit_report.make_row(
            pr="o/r#1",
            seat="flamingo-1",
            cr_mode="ready",
            review="light",
            tokens=100,
            cr_findings=2,
            fixed=1,
            rejected=1,
            na=0,
        ),
        coderabbit_report.make_row(
            pr="o/r#2",
            seat="flamingo-1",
            cr_mode="off",
            review="full",
            tokens=400,
            cr_findings=0,
            fixed=0,
            rejected=0,
            na=0,
        ),
        coderabbit_report.make_row(
            pr="o/r#3",
            seat="flamingo-2",
            cr_mode="ready",
            review="light",
            tokens=200,
            cr_findings=1,
            fixed=0,
            rejected=0,
            na=1,
        ),
    ]
    summary = coderabbit_report.summarize(rows)
    assert summary["light"]["count"] == 2
    assert summary["light"]["median_tokens"] == 150
    assert summary["full"]["count"] == 1
    assert summary["full"]["median_tokens"] == 400
    assert summary["coderabbit_fix_count"] == 1


def test_coderabbit_yaml_drafts_false_and_merge_wording():
    text = (
        Path(__file__).resolve().parents[2].joinpath(".coderabbit.yaml").read_text(encoding="utf-8")
    )
    assert "drafts: false" in text
    assert "fleet MRB seats" in text
    assert "Simon does every merge" not in text
    assert "ignore_title_keywords" in text
    assert "lesson(" in text
    assert "FAKE_" in text
    assert "UTF-8 without BOM" in text or "without BOM" in text
