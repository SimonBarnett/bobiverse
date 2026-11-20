"""FR #8427: needs_human false positives from holder_bored / infra-soft GIVEUPs.

FR #8375 made holder_bored never stamp needs_human. Rows stamped before that
(giveup_reason=holder_bored) starve the offer queue. The monitor check detects
and heals them; the chair predicate pins the false-positive definition.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
COMMON = REPO / "common" / "scripts"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(COMMON))

import gitclaim  # noqa: E402


def _write_queue(home: Path, *, unaccepted=None, accepted=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": list(unaccepted or []),
                "accepted": list(accepted or []),
                "done": [],
            }
        ),
        encoding="utf-8",
    )


def _row(repo="SimonBarnett/bobiverse", ident="#8391", **kw):
    row = {
        "repo": repo,
        "id": ident,
        "task": "FR",
        "needs_human": True,
        "giveup_reason": "holder_bored",
        "giveup_count": 2,
        "giveup_seats": "flamingo-10852,flamingo-22532",
    }
    row.update(kw)
    return row


def test_predicate_flags_infra_soft_needs_human():
    assert gitclaim.row_has_false_needs_human(_row()) is True
    assert gitclaim.row_has_false_needs_human(_row(giveup_reason="offer-timeout")) is True
    assert gitclaim.row_has_false_needs_human(_row(giveup_reason="hard ceiling 1800000ms")) is True
    assert gitclaim.row_has_false_needs_human(_row(giveup_reason="worktree-create-failed:no-clone")) is True
    # product give-up keeps needs_human
    assert gitclaim.row_has_false_needs_human(_row(giveup_reason="cannot review")) is False
    # no needs_human stamp is not a false positive
    assert gitclaim.row_has_false_needs_human(_row(needs_human=False)) is False
    # non-dict row never flags
    assert gitclaim.row_has_false_needs_human(None) is False


def test_heal_clears_false_needs_human_and_keeps_product(tmp_path):
    home = tmp_path / "jeeves"
    _write_queue(
        home,
        unaccepted=[
            _row(),
            _row(ident="#8396", giveup_reason="offer-timeout"),
            _row(ident="#8413", giveup_reason="cannot review"),
        ],
    )
    healed = gitclaim.heal_false_needs_human_for_infra_soft(home)
    assert set(healed) == {"SimonBarnett/bobiverse#8391", "SimonBarnett/bobiverse#8396"}

    doc = gitclaim.load_queue(home)
    rows = {r["id"]: r for r in doc["unaccepted"]}
    assert not rows["#8391"].get("needs_human")
    assert int(rows["#8391"].get("giveup_count") or 0) == 0
    assert not rows["#8391"].get("giveup_seats")
    assert not rows["#8396"].get("needs_human")
    # product give-up row is untouched and still needs human
    assert gitclaim.row_needs_human(rows["#8413"], "") is True


def _run_check(chair: Path, digest: Path) -> tuple[int, dict]:
    py = MON / "needs_human_false_positive.py"
    r = subprocess.run(
        [
            sys.executable,
            str(py),
            "--chair-home",
            str(chair),
            "--digest-home",
            str(digest),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MON),
    )
    line = (r.stdout or "").strip().splitlines()[-1]
    return r.returncode, json.loads(line)


def test_monitor_check_detects_and_heals(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(chair, unaccepted=[_row()])
    code, payload = _run_check(chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload.get("healed_count") == 1
    assert any("8391" in f for f in payload.get("findings") or [])

    # second run: nothing left to heal
    code2, payload2 = _run_check(chair, digest)
    assert code2 == 0, payload2
    assert payload2["ok"] is True
    assert payload2.get("healed_count") == 0


def test_monitor_ok_without_false_positive(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    _write_queue(
        chair,
        unaccepted=[_row(needs_human=False, giveup_reason="cannot review")],
    )
    code, payload = _run_check(chair, digest)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload.get("healed_count") == 0


def test_module_and_wrapper_exist():
    root = REPO / "jeeves"
    assert (root / "tools" / "monitor" / "needs_human_false_positive.py").is_file()
    assert (root / "scripts" / "Test-JeevesMonitorNeedsHumanFalsePositive.ps1").is_file()
    text = (root / "scripts" / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "needs_human_false_positive" in text
