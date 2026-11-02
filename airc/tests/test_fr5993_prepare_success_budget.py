"""FR #5993: successful PRIORITY prepare stays in budget; never reply-too-large."""
from __future__ import annotations

import json

import airc_priority as ap


def _long_unc_prep_dir() -> str:
    # Longest realistic UNC under Priority install roots (HR Smith class).
    return (
        r"\\hrs-fileserver.corp.example.local\priority$\HRSmith"
        r"\hrs-dev-live1\system\prep"
    )


def _success_prepare_payload(*, prep_dir: str | None = None) -> dict:
    return {
        "action": "prepare",
        "ok": True,
        "reason": "prepared",
        "ename": "WWWSHOWCUST",
        "exec": "REPPREPDIRECT2",
        "exec_id": 21848,
        "exec_type": "P",
        "exec_types": "P",
        "prep_file": "d21848.prp",
        "prep_dir": prep_dir if prep_dir is not None else _long_unc_prep_dir(),
        "prep_dir_source": "derived",
        "prep_dir_tried": [
            "override",
            "priority_root",
            "tabula_ini",
            "env_priority_prep",
            "env_priority_root",
        ],
        "prep_dir_derived_from": (
            r"\\hrs-fileserver.corp.example.local\priority$\HRSmith"
            r"\hrs-dev-live1"
        ),
        "prp_mtime_before": 1762095112.123456,
        "prp_mtime_after": 1762109465.654321,
        "prp_advanced": True,
        "upd": "N",
        "sql_faked": False,
        "sdk": {"ok": True, "errors": ["E" * 80, "F" * 80]},
    }


def test_fr5993_success_prepare_long_unc_stays_in_budget_keeps_core():
    payload = _success_prepare_payload()
    raw = "out id=aabb5993 seq=1 " + json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    )
    assert len(raw.encode("utf-8")) > ap.PRIORITY_REPLY_MAX_BYTES

    out, exit_code = ap.format_bounded_priority_out("aabb5993", payload, 0)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    assert exit_code == 0
    assert out.startswith("out id=aabb5993 seq=1 ")
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert body.get("reason") == "prepared"
    assert body.get("exec_id") == 21848
    assert body.get("prep_file") == "d21848.prp"
    assert body.get("prep_dir_source") == "derived"
    assert body.get("error") != "reply-too-large"
    assert "reply-too-large" not in out


def test_fr5993_success_prepare_never_flips_ok_true_to_exit_1():
    # Even with absurd path + noise, outcome stays ok/exit=0.
    payload = _success_prepare_payload(prep_dir=("\\\\" + "x" * 200 + r"\system\prep"))
    out, exit_code = ap.format_bounded_priority_out("deadbeef", payload, 0)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert exit_code == 0
    assert body.get("error") != "reply-too-large"


def test_fr5993_failure_still_reply_too_large_when_unshrinkable():
    # ok:false with a huge reason and no droppable detail keys -> fallback OK.
    payload = {
        "action": "prepare",
        "ok": False,
        "reason": "R" * 500,
        "ename": "HUGE",
    }
    out, exit_code = ap.format_bounded_priority_out("aabb0001", payload, 1)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is False
    assert body.get("error") == "reply-too-large"
    assert exit_code == 1
