"""FR #6592: operator !pin on bobiverse must survive FR #4512 re-inference."""
from __future__ import annotations

import gitclaim


def test_fr6592_operator_pin_bobiverse_gates_offer(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#6592",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/bobiverse#6592",
                    "title": "Jeeves still mentions require_machine=ionos in prose",
                    "body": "soft cue only; no dedicated pin line",
                    "labels": ["via-intake"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    out = gitclaim.set_require_machine_job(
        tmp_path, "SimonBarnett/bobiverse", "#6592", "ionos"
    )
    assert out["ok"] is True
    assert out["require_machine"] == "ionos"
    row = gitclaim.load_unaccepted(tmp_path)[0]
    assert row["require_machine"] == "ionos"
    assert str(row.get("require_machine_operator") or "").strip() in {"1", "true", "yes"}
    assert gitclaim.row_require_machine(row) == "ionos"
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "ionos"
    assert gitclaim.row_require_machine(row) == "ionos"


def test_fr6592_stale_non_operator_stamp_still_clears():
    """FR #4512: bare stamps without operator flag still clear on bobiverse."""
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "4478",
        "task": "FR",
        "title": "airc sparse bootstrap exits 0 without a .git directory",
        "body": "airc install root .git was not a directory",
        "labels": ["via-intake"],
        "require_machine": "ionos",
    }
    gitclaim._stamp_require_machine(row)
    stamped = str(row.get("require_machine") or "").strip().lower()
    assert stamped in {"", "any", "none", "*", "-"}
    assert gitclaim.row_require_machine(row) == ""


def test_fr6592_operator_unpin_survives_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#100",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/bobiverse#100",
                    "title": "prose mentions ionos install",
                    "body": "soft only",
                    "labels": ["via-intake"],
                    "require_machine": "ionos",
                    "require_machine_operator": "1",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    out = gitclaim.set_require_machine_job(
        tmp_path, "SimonBarnett/bobiverse", "#100", "any"
    )
    assert out["ok"] is True
    row = gitclaim.load_unaccepted(tmp_path)[0]
    assert row["require_machine"] == "any"
    assert str(row.get("require_machine_operator") or "").strip() in {"1", "true", "yes"}
    assert gitclaim.row_require_machine(row) == ""
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "any"
    assert gitclaim.row_require_machine(row) == ""


def test_fr6592_source_pins():
    text = (gitclaim.__file__ and open(gitclaim.__file__, encoding="utf-8").read()) or ""
    assert "require_machine_operator" in text
    assert "6592" in text
