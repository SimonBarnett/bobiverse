"""MRB #4746 hostile pins for FR #4745 Day Works / harvest-lesson pin narrowing."""
from __future__ import annotations

import gitclaim


def test_bare_dayworks_title_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="dayworks tip for docs",
            body="mentions dayworks only",
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#200",
        )
        == ""
    )


def test_living_umbrella_still_pins_dev1():
    assert (
        gitclaim.infer_require_machine(
            title="Day Works living umbrella remaining work",
            body="",
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#201",
        )
        == "ce-priority-dev1"
    )


def test_gate_e_still_pins_dev1():
    assert (
        gitclaim.infer_require_machine(
            title="Gate E smoke on Priority ERP",
            body="",
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#202",
        )
        == "ce-priority-dev1"
    )


def test_gates_d_g_out_of_scope_does_not_pin():
    """Parked specs listing Gates D-G as out-of-scope must not match Gates C-G."""
    assert (
        gitclaim.infer_require_machine(
            title="dayworks: FR: WP3 detailed spec",
            body="Out of scope: WP4 Neil load, Gates D-G.",
            labels=["feature-request"],
            repo="SimonBarnett/ce-priority",
            ident="#203",
        )
        == ""
    )


def test_dedicated_require_machine_line_pins_harvest_lesson():
    assert (
        gitclaim.infer_require_machine(
            title="lesson(harvest): tip",
            body="require_machine: ce-priority-dev1\n",
            labels=["harvest-lesson", "via-intake"],
            repo="SimonBarnett/ce-priority",
            ident="#204",
        )
        == "ce-priority-dev1"
    )


def test_row_require_machine_reinfers_harvest_lesson_clears_stamp():
    row = {
        "repo": "SimonBarnett/ce-priority",
        "id": "#29",
        "title": "lesson(harvest): ce-priority dayworks tip",
        "body": "docs-only",
        "labels": ["harvest-lesson"],
        "require_machine": "ce-priority-dev1",
        "line": "",
    }
    assert gitclaim.row_require_machine(row) == ""
