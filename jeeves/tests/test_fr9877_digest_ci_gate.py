"""FR #9877: digest_ci_gate BLOCK until all digest children CLOSED."""
from __future__ import annotations

import json
import sys

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
SCRIPTS = REPO / "jeeves" / "scripts"
sys.path.insert(0, str(MON))

import digest_ci_gate as dcg  # noqa: E402


def _all_closed_issues():
    states = {}
    for d in dcg.DEFAULT_DIGESTS:
        states[d] = "closed"
        for c in dcg.DEFAULT_DIGEST_CHILDREN.get(d, ()):
            states[c] = "closed"
    return states


def test_module_and_wrapper_exist():
    assert (MON / "digest_ci_gate.py").is_file()
    assert (SCRIPTS / "Test-JeevesMonitorDigestCiGate.ps1").is_file()
    invoke = (SCRIPTS / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "digest_ci_gate" in invoke


def test_classify_issue():
    assert dcg.classify_issue({"state": "closed"}) == "closed"
    assert dcg.classify_issue({"state": "OPEN"}) == "open"
    assert dcg.classify_issue(None) == "unknown"
    assert dcg.classify_issue({"state": "wat"}) == "unknown"


def test_two_open_children_block():
    digests = (9001,)
    children = {9001: (9002, 9003)}
    issues = {9001: "open", 9002: "open", 9003: "open"}
    ev = dcg.evaluate_gate(
        digests=digests,
        digest_children=children,
        issue_states=issues,
    )
    assert ev["verdict"] == "BLOCK_DIGEST_CI"
    assert ev["ok"] is False
    assert "digest_child_open" in ev["reasons"]
    assert ev["open_children"]


def test_one_child_closed_one_open_still_block():
    digests = (9001,)
    children = {9001: (9002, 9003)}
    issues = {9001: "open", 9002: "closed", 9003: "open"}
    ev = dcg.evaluate_gate(
        digests=digests,
        digest_children=children,
        issue_states=issues,
    )
    assert ev["verdict"] == "BLOCK_DIGEST_CI"
    assert "digest_child_open" in ev["reasons"]
    assert "9003" in ev["children"]
    assert ev["children"]["9003"] == "open"


def test_last_child_closed_allows_even_if_digest_open():
    digests = (9001,)
    children = {9001: (9002, 9003)}
    issues = {9001: "open", 9002: "closed", 9003: "closed"}
    ev = dcg.evaluate_gate(
        digests=digests,
        digest_children=children,
        issue_states=issues,
    )
    assert ev["verdict"] == "ALLOW_DIGEST_CI"
    assert ev["ok"] is True
    assert ev["reasons"] == []
    assert ev["open_children"] == []


def test_missing_child_state_unknown_fail_closed():
    digests = (9001,)
    children = {9001: (9002, 9003)}
    issues = {9001: "closed", 9002: "closed"}  # 9003 omitted
    ev = dcg.evaluate_gate(
        digests=digests,
        digest_children=children,
        issue_states=issues,
    )
    assert ev["verdict"] == "BLOCK_DIGEST_CI"
    assert "state_unknown" in ev["reasons"]


def test_empty_digests_undefined():
    ev = dcg.evaluate_gate(digests=[], digest_children={}, issue_states={})
    assert ev["verdict"] == "BLOCK_DIGEST_CI"
    assert "cohort_undefined" in ev["reasons"]


def test_digest_with_empty_children_undefined():
    ev = dcg.evaluate_gate(
        digests=(9001,),
        digest_children={9001: ()},
        issue_states={9001: "open"},
    )
    assert ev["verdict"] == "BLOCK_DIGEST_CI"
    assert "children_undefined" in ev["reasons"]


def test_default_cohort_child_open_blocks():
    issues = _all_closed_issues()
    child = dcg.DEFAULT_DIGEST_CHILDREN[dcg.DEFAULT_DIGESTS[0]][0]
    issues[child] = "open"
    ev = dcg.evaluate_gate(
        digests=dcg.DEFAULT_DIGESTS,
        digest_children=dcg.DEFAULT_DIGEST_CHILDREN,
        issue_states=issues,
    )
    assert ev["verdict"] == "BLOCK_DIGEST_CI"
    assert "digest_child_open" in ev["reasons"]
    assert child in ev["open_children"]


def test_default_cohort_all_closed_allows():
    ev = dcg.evaluate_gate(
        digests=dcg.DEFAULT_DIGESTS,
        digest_children=dcg.DEFAULT_DIGEST_CHILDREN,
        issue_states=_all_closed_issues(),
    )
    assert ev["verdict"] == "ALLOW_DIGEST_CI"
    assert ev["ok"] is True


def test_fixture_open_child_finding(tmp_path, monkeypatch):
    digests = list(dcg.DEFAULT_DIGESTS)
    child = dcg.DEFAULT_DIGEST_CHILDREN[digests[0]][0]
    issues = {str(k): {"state": "closed"} for k in _all_closed_issues()}
    issues[str(child)] = {"state": "open"}
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"issues": issues}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_MONITOR_DIGEST_CI_GATE_FIXTURE", str(fixture))
    payload, code = dcg.check(None)
    assert code == 1
    assert payload["verdict"] == "BLOCK_DIGEST_CI"
    assert payload["soft_ok"] is False
    assert payload["source"] == "fixture"
    assert payload["auth"] == "none"
    assert "digest_child_open" in payload["reasons"]


def test_fixture_all_closed_allow(tmp_path, monkeypatch):
    issues = {str(k): {"state": "closed"} for k in _all_closed_issues()}
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"issues": issues}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_MONITOR_DIGEST_CI_GATE_FIXTURE", str(fixture))
    payload, code = dcg.check(None)
    assert code == 0
    assert payload["verdict"] == "ALLOW_DIGEST_CI"
    assert payload["soft_ok"] is False
    assert payload["fr"] == 9877


def test_fixture_missing_rows_fail_closed(tmp_path, monkeypatch):
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"issues": {}}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_MONITOR_DIGEST_CI_GATE_FIXTURE", str(fixture))
    payload, code = dcg.check(None)
    assert code == 1
    assert payload["verdict"] == "BLOCK_DIGEST_CI"
    assert "state_unknown" in payload["reasons"] or payload["findings"]


def test_dry_run_exit_0():
    code = dcg.main(["--dry-run"])
    assert code == 0


def test_monitor_start_and_docs_list_check():
    start = (REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "digest_ci_gate" in start
    fr_digest = (
        REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-digest" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "9877" in fr_digest
    assert "digest_ci_gate" in fr_digest or "ALLOW_DIGEST_CI" in fr_digest
    note = (REPO / "jeeves" / "docs" / "fr-digest-vs-hold-vs-depends-on.md").read_text(
        encoding="utf-8"
    )
    assert "9877" in note
    invoke = (SCRIPTS / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "digest_ci_gate" in invoke
