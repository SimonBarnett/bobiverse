"""FR #9847: tip_merge_gate NO_INSTALL until tip PRs + digests/children closed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
SCRIPTS = REPO / "jeeves" / "scripts"
sys.path.insert(0, str(MON))

import tip_merge_gate as tmg  # noqa: E402


def _all_merged_prs(tip=None):
    tip = list(tip if tip is not None else tmg.DEFAULT_TIP_PRS)
    return {n: "merged" for n in tip}


def _all_closed_issues():
    states = {}
    for d in tmg.DEFAULT_DIGESTS:
        states[d] = "closed"
        for c in tmg.DEFAULT_DIGEST_CHILDREN.get(d, ()):
            states[c] = "closed"
    return states


def test_module_and_wrapper_exist():
    assert (MON / "tip_merge_gate.py").is_file()
    assert (SCRIPTS / "Test-JeevesMonitorTipMergeGate.ps1").is_file()
    invoke = (SCRIPTS / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "tip_merge_gate" in invoke


def test_classify_pr_merged_open_closed():
    assert tmg.classify_pr({"state": "closed", "merged": True}) == "merged"
    assert tmg.classify_pr({"state": "closed", "merged_at": "2026-11-24T00:00:00Z"}) == "merged"
    assert tmg.classify_pr({"state": "open", "merged": False}) == "open"
    assert tmg.classify_pr({"state": "closed", "merged": False}) == "closed_unmerged"
    assert tmg.classify_pr(None) == "unknown"


def test_tip_pr_open_no_install():
    tip = list(tmg.DEFAULT_TIP_PRS)
    pr = _all_merged_prs(tip)
    pr[tip[0]] = "open"
    ev = tmg.evaluate_gate(
        tip_prs=tip,
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states=pr,
        issue_states=_all_closed_issues(),
    )
    assert ev["verdict"] == "NO_INSTALL"
    assert ev["step"] == 1
    assert "tip_pr_open" in ev["reasons"]
    assert ev["ok"] is False


def test_tip_pr_closed_unmerged_no_install():
    tip = list(tmg.DEFAULT_TIP_PRS)
    pr = _all_merged_prs(tip)
    pr[tip[1]] = "closed_unmerged"
    ev = tmg.evaluate_gate(
        tip_prs=tip,
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states=pr,
        issue_states=_all_closed_issues(),
    )
    assert ev["verdict"] == "NO_INSTALL"
    assert ev["step"] == 1
    assert "tip_pr_closed_unmerged" in ev["reasons"]


def test_all_prs_merged_digest_9830_open_step2():
    tip = list(tmg.DEFAULT_TIP_PRS)
    issues = _all_closed_issues()
    issues[9830] = "open"
    ev = tmg.evaluate_gate(
        tip_prs=tip,
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states=_all_merged_prs(tip),
        issue_states=issues,
    )
    assert ev["verdict"] == "NO_INSTALL"
    assert ev["step"] == 2
    assert "digest_open" in ev["reasons"]


def test_digest_closed_child_open():
    tip = list(tmg.DEFAULT_TIP_PRS)
    issues = _all_closed_issues()
    child = tmg.DEFAULT_DIGEST_CHILDREN[9830][0]
    issues[child] = "open"
    ev = tmg.evaluate_gate(
        tip_prs=tip,
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states=_all_merged_prs(tip),
        issue_states=issues,
    )
    assert ev["verdict"] == "NO_INSTALL"
    assert ev["step"] == 2
    assert "digest_child_open" in ev["reasons"]


def test_missing_fixture_row_unknown():
    tip = list(tmg.DEFAULT_TIP_PRS)
    pr = _all_merged_prs(tip)
    # omit one tip PR from states -> unknown via setdefault in check(); pure eval:
    del pr[tip[0]]
    ev = tmg.evaluate_gate(
        tip_prs=tip,
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states=pr,
        issue_states=_all_closed_issues(),
    )
    assert ev["verdict"] == "NO_INSTALL"
    assert "state_unknown" in ev["reasons"]


def test_empty_cohort_undefined():
    ev = tmg.evaluate_gate(
        tip_prs=[],
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states={},
        issue_states={},
    )
    assert ev["verdict"] == "NO_INSTALL"
    assert "cohort_undefined" in ev["reasons"]


def test_fully_closed_ok_for_receipt():
    tip = list(tmg.DEFAULT_TIP_PRS)
    ev = tmg.evaluate_gate(
        tip_prs=tip,
        digests=tmg.DEFAULT_DIGESTS,
        digest_children=tmg.DEFAULT_DIGEST_CHILDREN,
        pr_states=_all_merged_prs(tip),
        issue_states=_all_closed_issues(),
    )
    assert ev["verdict"] == "OK_FOR_RECEIPT"
    assert ev["step"] == 3
    assert ev["ok"] is True
    assert ev["reasons"] == []


def test_fixture_open_tip_finding(tmp_path, monkeypatch):
    tip = list(tmg.DEFAULT_TIP_PRS)
    prs = {str(n): {"state": "closed", "merged": True} for n in tip}
    prs[str(tip[0])] = {"state": "open", "merged": False}
    issues = {str(k): {"state": "closed"} for k in _all_closed_issues()}
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"prs": prs, "issues": issues}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_MONITOR_TIP_MERGE_GATE_FIXTURE", str(fixture))
    payload, code = tmg.check(None)
    assert code == 1
    assert payload["verdict"] == "NO_INSTALL"
    assert payload["soft_ok"] is False
    assert payload["source"] == "fixture"
    assert payload["auth"] == "none"
    assert "tip_pr_open" in payload["reasons"]


def test_fixture_pass(tmp_path, monkeypatch):
    tip = list(tmg.DEFAULT_TIP_PRS)
    prs = {str(n): {"state": "closed", "merged": True} for n in tip}
    issues = {str(k): {"state": "closed"} for k in _all_closed_issues()}
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"prs": prs, "issues": issues}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_MONITOR_TIP_MERGE_GATE_FIXTURE", str(fixture))
    payload, code = tmg.check(None)
    assert code == 0
    assert payload["verdict"] == "OK_FOR_RECEIPT"
    assert payload["soft_ok"] is False


def test_fixture_missing_rows_fail_closed(tmp_path, monkeypatch):
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"prs": {}, "issues": {}}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_MONITOR_TIP_MERGE_GATE_FIXTURE", str(fixture))
    payload, code = tmg.check(None)
    assert code == 1
    assert payload["verdict"] == "NO_INSTALL"
    assert "state_unknown" in payload["reasons"] or payload["findings"]


def test_dry_run_exit_0():
    code = tmg.main(["--dry-run"])
    assert code == 0


def test_monitor_start_lists_check():
    start = (REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "tip_merge_gate" in start
    assert "tip_merge_gate" in (
        SCRIPTS / "Invoke-JeevesMonitorCheck.ps1"
    ).read_text(encoding="utf-8-sig")


def test_arm_doc_exists_and_lists_cohort():
    arm = REPO / "jeeves" / "docs" / "ARM_JEEVES_PRS_THEN_9830_9148_WALRUS.md"
    assert arm.is_file()
    text = arm.read_text(encoding="utf-8")
    for n in tmg.DEFAULT_TIP_PRS:
        assert str(n) in text
    assert "9830" in text and "9148" in text
    assert "OK_FOR_RECEIPT" in text
    assert "NO_INSTALL" in text
