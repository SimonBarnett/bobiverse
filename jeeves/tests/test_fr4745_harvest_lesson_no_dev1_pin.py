"""FR #4745: ce-priority harvest-lesson MRB and bare dayworks/WP3 titles must not stamp DEV1."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _digest(home, machines):
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {str(w): {"state": "idle"} for w in workers}
    bobreport.save_digest(home, doc)


def test_ce_priority_harvest_lesson_pr_does_not_pin_dev1():
    """Lesson PR #29 class: dayworks in the tip title is not an explicit machine pin."""
    assert (
        gitclaim.infer_require_machine(
            title=(
                "lesson(harvest): ce-priority dayworks: harvest-agent-skills is locked; "
                "landing a Harvested lessons bullet needs SimonBarnett"
            ),
            body=(
                "MRB (light triage): useful?\n"
                "Target skill book: harvest\n"
                "Lessons:\n"
                "- ce-priority dayworks: harvest-agent-skills is locked\n"
            ),
            labels=["via-intake", "harvest-lesson"],
            repo="SimonBarnett/ce-priority",
            ident="#29",
        )
        == ""
    )


def test_ce_priority_wp3_spec_fr_without_living_or_gates_does_not_pin():
    """Issue #17 class: parked WP3 spec mentions dayworks/WP3 but is not live DEV1 work."""
    assert (
        gitclaim.infer_require_machine(
            title="dayworks: FR: WP3 ZCLA_ELEDITLOGREM + ZCLA_DWDESCREV detailed spec (unblock O1)",
            body=(
                "Standing rules forbid inventing ENAMEs.\n"
                "Gate A/B regression is shipping; do not build WP3 until answered.\n"
                "Out of scope: WP4 Neil load, Gates D-G.\n"
            ),
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#17",
        )
        == ""
    )


def test_stamp_clears_sticky_dev1_on_harvest_lesson():
    row = {
        "repo": "SimonBarnett/ce-priority",
        "task": "MRB",
        "id": "#29",
        "title": "lesson(harvest): ce-priority dayworks tip",
        "body": "docs-only harvest tip",
        "labels": ["harvest-lesson", "via-intake"],
        "require_machine": "ce-priority-dev1",
        "url": "https://github.com/SimonBarnett/ce-priority/pull/29",
    }
    claim = gitclaim.GitClaim(
        event="pull_request",
        action="opened",
        repo="SimonBarnett/ce-priority",
        task="MRB",
        id="#29",
        title=row["title"],
        body=row["body"],
        labels=tuple(row["labels"]),
        line="",
        harvest_lesson=True,
        opened_by="win-mpre8vi4u6u-14652",
    )
    gitclaim._stamp_require_machine(row, claim)
    stamped = str(row.get("require_machine") or "").strip().lower()
    assert stamped in {"", "any", "*", "none", "-"}
    assert gitclaim.row_require_machine(row) == ""


def test_assign_harvest_lesson_to_marchhare_accepted(tmp_path, monkeypatch):
    """!assign to a non-author seat must not refuse 'pinned to another machine'."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(
        home,
        {
            "marchhare": [1656],
            "ce-priority-dev1": [1],
            "win-mpre8vi4u6u": [14652],
        },
    )
    row = {
        "repo": "SimonBarnett/ce-priority",
        "task": "MRB",
        "id": "#29",
        "seq": 1,
        "ts": "t",
        "title": "lesson(harvest): ce-priority dayworks tip",
        "body": "docs-only",
        "labels": ["harvest-lesson", "via-intake"],
        "require_machine": "ce-priority-dev1",
        "url": "https://github.com/SimonBarnett/ce-priority/pull/29",
        "author_seat": "win-mpre8vi4u6u-14652",
        "line": "MRB SimonBarnett/ce-priority#29",
    }
    gitclaim._stamp_require_machine(
        row,
        gitclaim.GitClaim(
            event="pull_request",
            action="opened",
            repo=row["repo"],
            task="MRB",
            id="#29",
            title=row["title"],
            body=row["body"],
            labels=tuple(row["labels"]),
            line="",
            harvest_lesson=True,
            opened_by="win-mpre8vi4u6u-14652",
        ),
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, detail = gitclaim.assign_row(
        home,
        "marchhare-1656",
        "SimonBarnett/ce-priority",
        "MRB",
        "29",
        pr_exists=lambda *a, **k: True,
        is_pull=lambda *a, **k: True,
        issue_open=lambda *a, **k: True,
    )
    assert st == "ok", detail
    assert "pinned to another machine" not in str(detail).lower()


def test_explicit_needs_label_still_pins_harvest_lesson():
    assert (
        gitclaim.infer_require_machine(
            title="lesson(harvest): needs live box",
            body="explicit pin",
            labels=["harvest-lesson", "needs-ce-priority-dev1"],
            repo="SimonBarnett/ce-priority",
            ident="#40",
        )
        == "ce-priority-dev1"
    )
