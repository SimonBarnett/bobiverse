"""FR #2670: via-intake CRITICAL: issues must be queued; clear-gate must agree with intake.

Deadlock: CRITICAL_SPAM_TITLE_RE skipped every ^CRITICAL: title (never offered) while
workers/UAT still treated the open issue as blocking — seats sat at 0 offerable.
"""
from __future__ import annotations

import gitclaim


def test_fr2670_via_intake_critical_prefix_is_offerable():
    title = "CRITICAL: chair re-offer of agentic_fomprep#11 (real work)"
    assert gitclaim.issue_skip_fr_reason(title=title, labels=("via-intake",)) is None
    assert gitclaim.issue_blocks_repo_uat(title=title, labels=("via-intake",)) is True


def test_fr2670_feature_request_critical_prefix_is_offerable():
    title = "CRITICAL: bob-ear startworker frozen root"
    assert gitclaim.issue_skip_fr_reason(title=title, labels=("feature-request",)) is None
    assert gitclaim.issue_blocks_repo_uat(title=title, labels=("feature-request",)) is True


def test_fr2670_spam_reoffer_and_drain_still_skipped():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="CRITICAL: 5th re-offer of agentic_fomprep#11",
            labels=("via-intake",),
        )
        == "critical_spam_title"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="CRITICAL: drain FR-unaccepted loop again",
            labels=("via-intake",),
        )
        == "critical_spam_title"
    )
    # Spam must not block repo UAT (same exclusion as intake).
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="CRITICAL: 3rd re-offer of something",
            labels=("via-intake",),
        )
        is False
    )


def test_fr2670_bare_critical_without_intake_labels_still_skipped():
    """Seat-filed CRITICAL: without via-intake/feature-request stays spam (FR #628)."""
    assert (
        gitclaim.issue_skip_fr_reason(title="CRITICAL: Jeeves chair DOWN again", labels=())
        == "critical_spam_title"
    )
    assert (
        gitclaim.issue_blocks_repo_uat(title="CRITICAL: Jeeves chair DOWN again", labels=())
        is False
    )


def test_fr2670_resync_queues_via_intake_critical(tmp_path, monkeypatch):
    """Open via-intake CRITICAL: issue becomes an FR row (fails on tip that skips all CRITICAL:)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    issues = [
        {
            "number": 2562,
            "title": "CRITICAL: re-offered agentic_fomprep#11 mrb-fail verdict board",
            "body": "via intake",
            "state": "open",
            "labels": [{"name": "via-intake"}],
        }
    ]

    def fetch(url: str):
        if "/pulls" in url:
            return []
        return issues

    res = gitclaim.resync_from_github(
        tmp_path, ["SimonBarnett/bobiverse"], fetch_json=fetch
    )
    assert res.get("failed") in (None, [], 0) or not res.get("failed")
    rows = gitclaim.load_unaccepted(tmp_path)
    frs = [r for r in rows if r.get("task") == "FR" and r.get("id") == "#2562"]
    assert len(frs) == 1, rows
    assert "CRITICAL:" in str(frs[0].get("title") or frs[0].get("line") or "")
