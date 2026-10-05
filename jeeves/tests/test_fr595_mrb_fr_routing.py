"""FR #595: never invent /pull/{issue_id} for MRB; skip mrb/mrb-pass FR boards.

FR #2464: mrb-fail is offerable remediation (no longer in SKIP_FR_LABELS).
"""
from __future__ import annotations

import gitclaim


def test_skip_fr_labels_include_verdict_boards():
    for lab in ("mrb", "mrb-pass"):
        assert lab in gitclaim.SKIP_FR_LABELS
        assert gitclaim.issue_skip_fr_reason(title="FR: x", labels=(lab,)) == f"label:{lab}"
    assert "mrb-fail" not in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="FR: x", labels=("mrb-fail",)) is None


def test_mrb_verdict_labels_do_not_enqueue_as_fr():
    for lab in ("mrb", "mrb-pass"):
        claim = gitclaim.claim_from_payload(
            "issues",
            {
                "action": "opened",
                "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
                "issue": {
                    "number": 9,
                    "title": "MRB board",
                    "body": "",
                    "state": "open",
                    "labels": [{"name": lab}, {"name": "feature-request"}],
                },
            },
        )
        assert claim is None, lab


def test_mrb_without_url_does_not_invent_pull_from_issue_id():
    """Regression: MRB for issue #227 must never become .../pull/227."""
    line = gitclaim.format_assign_line(
        "marchhare-35600",
        {
            "task": "MRB",
            "repo": "SimonBarnett/bobiverse",
            "id": "#227",
        },
    )
    assert "pull/227" not in line
    assert "marchhare-35600: MRB SimonBarnett/bobiverse#227" in line
    assert gitclaim.resolve_assign_url(
        {"task": "MRB", "repo": "SimonBarnett/bobiverse", "id": "#227"}
    ) == ""


def test_mrb_with_explicit_pr_id_builds_pull_url():
    url = gitclaim.resolve_assign_url(
        {
            "task": "MRB",
            "repo": "SimonBarnett/bobiverse",
            "id": "#240",
            "pr_id": "#240",
        }
    )
    assert url == "https://github.com/SimonBarnett/bobiverse/pull/240"


def test_mrb_keeps_real_pull_url():
    url = gitclaim.resolve_assign_url(
        {
            "task": "MRB",
            "repo": "SimonBarnett/bobiverse",
            "id": "#240",
            "url": "https://github.com/SimonBarnett/bobiverse/pull/240",
        }
    )
    assert url.endswith("/pull/240")


def test_mrb_issues_url_not_offerable():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#227",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/227",
    }
    assert gitclaim.mrb_row_offerable(row) is False


def test_mrb_missing_pull_url_not_offerable():
    assert (
        gitclaim.mrb_row_offerable(
            {"task": "MRB", "repo": "SimonBarnett/bobiverse", "id": "#227"}
        )
        is False
    )


def test_mrb_real_pull_offerable():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#240",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/240",
    }
    assert gitclaim.mrb_row_offerable(row) is True


def test_fr_still_invents_issues_url():
    url = gitclaim.resolve_assign_url(
        {"task": "FR", "repo": "SimonBarnett/bobiverse", "id": "#595"}
    )
    assert url == "https://github.com/SimonBarnett/bobiverse/issues/595"


def test_offer_skips_fake_mrb_pull_and_offers_next(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#227",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    # no url — classic invent trap
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#595",
                    "seq": 2,
                    "ts": "t",
                    "line": "FR: harden",
                    "title": "FR: harden",
                    "labels": ["feature-request"],
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/595",
                },
            ],
            "accepted": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#595"
    assert job["task"] == "FR"
    line = gitclaim.format_assign_line("marchhare-1", job)
    assert "pull/227" not in line


def test_offer_skips_stale_pull_when_pr_exists_false(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#227",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/227",
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#240",
                    "seq": 2,
                    "ts": "t",
                    "line": "x",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/240",
                },
            ],
            "accepted": [],
        },
    )

    def pr_exists(repo: str, num: str) -> bool:
        return num == "240"

    st, job = gitclaim.offer_focus_top(
        tmp_path, "marchhare-1", "#marchhare", pr_exists=pr_exists
    )
    assert st == "ok"
    assert job["id"] == "#240"
    assert "pull/240" in str(job.get("url") or "")


def test_offer_skips_mrb_pass_row_even_when_only_line_set(tmp_path, monkeypatch):
    """Legacy row: empty title, labels + line still skip at offer (priority cannot override)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#9",
                    "seq": 1,
                    "ts": "t",
                    "line": "mrb-pass board for agentic_fomprep",
                    "labels": ["mrb-pass", "feature-request"],
                    # title intentionally missing
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#595",
                    "seq": 2,
                    "ts": "t",
                    "line": "FR: real",
                    "title": "FR: real",
                    "labels": ["feature-request"],
                },
            ],
            "accepted": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#595"


def test_prune_drops_mrb_verdict_and_fake_mrb_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rows = [
        {
            "repo": "o/r",
            "task": "FR",
            "id": "#1",
            "seq": 1,
            "ts": "t",
            "line": "keep",
            "title": "FR: keep",
        },
        {
            "repo": "o/r",
            "task": "FR",
            "id": "#9",
            "seq": 2,
            "ts": "t",
            "line": "mrb-pass board",
            "labels": ["mrb-pass"],
        },
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "MRB",
            "id": "#227",
            "seq": 3,
            "ts": "t",
            "line": "fake",
            # no pull url
        },
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "MRB",
            "id": "#240",
            "seq": 4,
            "ts": "t",
            "line": "real",
            "url": "https://github.com/SimonBarnett/bobiverse/pull/240",
        },
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": rows, "accepted": []}
    )
    res = gitclaim.prune_unassignable_queue(tmp_path)
    assert res["ok"]
    left = gitclaim.load_unaccepted(tmp_path)
    assert [r["id"] for r in left] == ["#1", "#240"]

def test_skip_fr_underscore_verdict_aliases():
    assert "mrb_pass" in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="FR: x", labels=("mrb_pass",)).startswith("label:")
    # FR #2464: mrb_fail is offerable remediation.
    assert "mrb_fail" not in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="FR: x", labels=("mrb_fail",)) is None


def test_line_only_mrb_pass_text_skips_without_labels(tmp_path, monkeypatch):
    """MRB #603 / FR #2464: empty labels + line text 'mrb-pass' still skips; mrb-fail does not."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    assert gitclaim.row_skip_fr_reason(
        {"line": "mrb-pass board for agentic_fomprep#9", "labels": (), "title": ""}
    )
    assert (
        gitclaim.row_skip_fr_reason(
            {"line": "mrb-fail remediation for agentic_fomprep#11", "labels": (), "title": ""}
        )
        is None
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#9",
                    "seq": 1,
                    "ts": "t",
                    "line": "mrb-pass board for agentic_fomprep#9",
                    # no labels, no title — text skip for mrb-pass
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#595",
                    "seq": 2,
                    "ts": "t",
                    "line": "FR: harden MRB/FR routing",
                    "title": "FR: harden MRB/FR routing: reject fake pull URLs",
                    "labels": ["feature-request"],
                },
            ],
            "accepted": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#595"


def test_real_fr_title_with_mrb_slash_not_skipped():
    """Bare 'MRB' in a real FR title must not trip text skip (labels-only for bare mrb)."""
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: harden MRB/FR routing: reject fake pull URLs",
            labels=("feature-request",),
        )
        is None
    )


def test_mrb_cross_repo_pull_url_not_offerable():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#240",
        "url": "https://github.com/other/owner/pull/999",
    }
    assert gitclaim.mrb_row_offerable(row) is False
