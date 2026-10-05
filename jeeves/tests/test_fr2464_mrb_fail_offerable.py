"""FR #2464: mrb-fail remediation is offerable; mrb-pass / mrb-home still skipped."""
from __future__ import annotations

import gitclaim


def test_mrb_fail_offerable_not_skipped():
    assert gitclaim.issue_skip_fr_reason(
        title="MRB FAIL: formlimited-audit-in-clause 7db4bcc",
        labels=("mrb", "mrb-fail"),
        state="open",
    ) is None
    assert gitclaim.issue_skip_fr_reason(
        title="MRB FAIL: priority-skills-catalog abc",
        labels=("mrb", "mrb-fail"),
        state="open",
    ) is None


def test_mrb_pass_still_skipped():
    why = gitclaim.issue_skip_fr_reason(
        title="MRB PASS-nits: shell-compile-install-v2-spec-0.1",
        labels=("mrb", "mrb-pass"),
        state="open",
    )
    assert why == "label:mrb-pass"


def test_mrb_home_still_skipped():
    why = gitclaim.issue_skip_fr_reason(
        title="FR: Priority agent skills catalog in v2",
        labels=("feature-request", "mrb-home"),
        state="open",
    )
    assert why == "label:mrb-home"


def test_mrb_fail_with_mrb_home_still_skipped():
    # evergreen FAIL board stays non-assignable
    why = gitclaim.issue_skip_fr_reason(
        title="MRB FAIL: mrb-wcf-walker-eshbel-docs 80d8ce4",
        labels=("mrb", "mrb-fail", "mrb-home"),
        state="open",
    )
    assert why == "label:mrb-home"


def test_skip_fr_labels_exclude_mrb_fail():
    assert "mrb-fail" not in gitclaim.SKIP_FR_LABELS
    assert "mrb_fail" not in gitclaim.SKIP_FR_LABELS
    assert "mrb" not in gitclaim.SKIP_FR_LABELS
    assert "mrb-pass" in gitclaim.SKIP_FR_LABELS
    assert "mrb-home" in gitclaim.SKIP_FR_LABELS


def test_resync_enqueues_mrb_fail_not_pass(tmp_path):
    """Desired FR set from GitHub-shaped issues includes FAIL, excludes PASS."""
    issues = [
        {
            "number": 11,
            "title": "MRB FAIL: formlimited-audit-in-clause 7db4bcc",
            "body": "hostile FAIL — fix the branch",
            "state": "open",
            "labels": [{"name": "mrb"}, {"name": "mrb-fail"}],
        },
        {
            "number": 20,
            "title": "MRB PASS-nits: shell-compile-install-v2-spec-0.1",
            "body": "PASS receipt",
            "state": "open",
            "labels": [{"name": "mrb"}, {"name": "mrb-pass"}],
        },
        {
            "number": 56,
            "title": "FR: WP0 live proof",
            "body": "real FR",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        },
    ]

    def fetch(url, token=None, **kwargs):
        u = str(url)
        if "/issues" in u and "/pulls" not in u:
            return issues
        if "/pulls" in u:
            return []
        return []

    res = gitclaim.resync_from_github(tmp_path, ["SimonBarnett/agentic_fomprep"], fetch_json=fetch)
    q = gitclaim.load_queue(tmp_path)
    ids = {(r.get("task"), str(r.get("id"))) for r in (q.get("unaccepted") or [])}
    assert ("FR", "#11") in ids, ids
    assert ("FR", "#56") in ids, ids
    assert ("FR", "#20") not in ids, ids
