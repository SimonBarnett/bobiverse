"""FR #9114: MRB hold gate uses live linked-FR hold labels, not stale PR HOLD comments."""
from __future__ import annotations

import mrb_merge_gate as gate


def _c(assoc: str, body: str, created: str = "2026-11-21T00:00:00Z") -> dict:
    return {
        "author_association": assoc,
        "body": body,
        "created_at": created,
        "user": {"login": "SimonBarnett"},
    }


def test_parse_closes_and_hold_comment_fr_numbers():
    body = "Closes SimonBarnett/bobiverse#8677\nAlso see FR #9000."
    comments = [_c("OWNER", "HOLD: linked FR is phase-gated. Do not merge until FR #8677 hold is removed.")]
    nums = gate.linked_fr_issue_numbers(body, comments)
    assert 8677 in nums
    assert 9000 in nums


def test_stale_pr_hold_comment_ignored_when_linked_fr_unheld():
    """Class of #8748: HOLD comment remains after FR hold label is gone."""
    comments = [
        _c("OWNER", "HOLD: linked FR is phase-gated. Do not merge until FR `hold` is removed."),
        _c(
            "OWNER",
            "## MRB board\n\n**Verdict:** PASS\n**MRB PASS @ abc123",
            "2026-11-22T22:00:00Z",
        ),
    ]
    ok, reason = gate.evaluate_merge_gate(
        comments,
        linked_fr_hold=None,
        linked_frs_checked=True,
    )
    assert ok is True
    assert reason == ""


def test_linked_fr_hold_label_still_refuses():
    comments = [
        _c(
            "OWNER",
            "## MRB board\n\n**Verdict:** PASS\n**MRB PASS @ abc123",
        ),
    ]
    ok, reason = gate.evaluate_merge_gate(
        comments,
        linked_fr_hold="SimonBarnett/bobiverse#8677 label=hold",
        linked_frs_checked=True,
    )
    assert ok is False
    assert "linked FR hold" in reason
    assert "8677" in reason


def test_legacy_comment_hold_when_linked_frs_not_checked():
    """Unit callers without linked-FR resolution keep FR #3928 comment hold."""
    comments = [
        _c("OWNER", "HOLD: do not merge this PR"),
        _c("OWNER", "## MRB board\n\n**Verdict:** PASS\n**MRB PASS @ abc"),
    ]
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "owner hold active" in reason


def test_issue_labels_detect_hold():
    assert gate.issue_has_hold_label([{"name": "feature-request"}, {"name": "hold"}]) is True
    assert gate.issue_has_hold_label([{"name": "on-hold"}]) is True
    assert gate.issue_has_hold_label([{"name": "feature-request"}]) is False


def test_resolve_linked_fr_hold_with_fake_labels():
    body = "Closes SimonBarnett/bobiverse#8677"
    comments = [_c("OWNER", "HOLD: linked FR #8677 phase-gated.")]

    def held(repo, n, token=None):
        return [{"name": "hold"}] if int(n) == 8677 else []

    def clear(repo, n, token=None):
        return [{"name": "feature-request"}]

    checked, reason = gate.resolve_linked_fr_hold(
        "SimonBarnett/bobiverse", body, comments, fetch_labels=held
    )
    assert checked is True
    assert reason and "8677" in reason

    checked2, reason2 = gate.resolve_linked_fr_hold(
        "SimonBarnett/bobiverse", body, comments, fetch_labels=clear
    )
    assert checked2 is True
    assert reason2 is None


def test_skill_documents_fr9114_linked_fr_hold():
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath(
        "bob", ".grok", "skills", "bobiverse-bob-job-mrb", "SKILL.md"
    ).read_text(encoding="utf-8")
    low = text.lower()
    assert "#9114" in text
    assert "stale" in low
    assert ("linked fr" in low) or ("linked-fr" in low) or ("linked issue" in low)


def test_harvest_documents_fr9114():
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath(
        "common", ".grok", "skills", "harvest", "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "#9114" in text or "stale PR HOLD" in text or "live FR hold" in text
