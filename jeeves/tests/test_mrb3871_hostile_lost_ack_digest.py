"""MRB #3871 hostile pins for FR #3867 lost-ACK digest reconcile.

Product merge: PR #3871. Pins that must survive on main:
- same numeric id across two repos: only the digest repo_short promotes
- already-accepted matching row: reconcile does not duplicate into accepted
- troubleshooting skill names LOST_ACK_RESTART / reconcile_lost_ack_from_digest
- irc_agent session() wires reconcile_lost_ack_from_digest (FR #3867)
"""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "marchhare-960"
WORK = "a-search FR #1018"
REPO_A = "SimonBarnett/a-search"
REPO_B = "SimonBarnett/bobiverse"
ROOT = Path(__file__).resolve().parents[2]


def _setup(home: Path, monkeypatch, *, work: str = WORK) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": work,
        "worker_list": [
            {
                "nick": NICK,
                "state": "idle",
                "work": "",
                "updated": "2026-10-10T06:01:13Z",
            }
        ],
        "workers": {
            "960": {
                "pid": "960",
                "nick": NICK,
                "state": "running",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, *, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(unaccepted), "accepted": list(accepted or [])},
    )


def _row(repo: str, issue_id: str, **extra) -> dict:
    num = str(issue_id).lstrip("#")
    base = {
        "repo": repo,
        "task": "FR",
        "id": f"#{num}",
        "seq": int(num),
        "url": f"https://github.com/{repo}/issues/{num}",
    }
    base.update(extra)
    return base


def test_mrb3871_hostile_repo_scoped_promote_same_numeric_id(tmp_path, monkeypatch):
    """Digest 'a-search FR #1018' must not promote bobiverse FR #1018."""
    _setup(tmp_path, monkeypatch, work=WORK)
    offer_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    _queue(
        tmp_path,
        unaccepted=[
            _row(REPO_A, "#1018", offered_to=NICK, offered_ts=offer_ts),
            _row(REPO_B, "#1018"),
        ],
    )
    n = gitclaim.reconcile_lost_ack_from_digest(tmp_path)
    assert n == 1
    q = gitclaim.load_queue(tmp_path)
    acc = q.get("accepted") or []
    unacc = q.get("unaccepted") or []
    assert len(acc) == 1
    assert acc[0]["repo"] == REPO_A
    assert str(acc[0]["id"]) == "#1018"
    assert str(acc[0].get("reconcile") or "") == "LOST_ACK_RESTART"
    assert any(r.get("repo") == REPO_B and str(r.get("id")) == "#1018" for r in unacc)


def test_mrb3871_hostile_already_accepted_drops_unaccepted_twin(tmp_path, monkeypatch):
    """Matching row already in accepted: drop unaccepted twin (no double-offer, no dup accepted)."""
    _setup(tmp_path, monkeypatch, work=WORK)
    offer_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    existing = _row(REPO_A, "#1018", nick=NICK, accepted_ts=offer_ts)
    twin = _row(REPO_A, "#1018", offered_to=NICK, offered_ts=offer_ts)
    _queue(tmp_path, unaccepted=[twin], accepted=[existing])
    n = gitclaim.reconcile_lost_ack_from_digest(tmp_path)
    assert n >= 1  # twin drop counted so queue write persists (no new accepted row)
    q = gitclaim.load_queue(tmp_path)
    assert len(q.get("accepted") or []) == 1
    assert q.get("unaccepted") == []
    assert not any(
        str(r.get("reconcile") or "") == "LOST_ACK_RESTART"
        for r in (q.get("accepted") or [])
    )


def test_mrb3871_hostile_parse_full_owner_repo_form():
    parsed = gitclaim.parse_digest_work("SimonBarnett/a-search FR #1018")
    assert parsed is not None
    assert parsed["task"] == "FR"
    assert parsed["id"] == "#1018"
    assert parsed["repo"] == "SimonBarnett/a-search"
    assert parsed["repo_short"] == "a-search"
    assert gitclaim.row_matches_digest_work(
        _row(REPO_A, "#1018"), "SimonBarnett/a-search FR #1018"
    )
    assert not gitclaim.row_matches_digest_work(
        _row(REPO_B, "#1018"), "SimonBarnett/a-search FR #1018"
    )


def test_mrb3871_hostile_skill_and_session_wire_contiguous():
    skill = (
        ROOT
        / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "LOST_ACK_RESTART" in skill
    assert "reconcile_lost_ack_from_digest" in skill
    assert "FR #3867" in skill
    # Contiguous: do not FR #1714-clear while unaccepted still matches.
    assert "Do not FR #1714-clear map" in skill or "do not FR #1714-clear" in skill.lower()

    agent = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    assert "reconcile_lost_ack_from_digest" in agent
    assert "FR #3867" in agent


def test_mrb3871_hostile_utf8_no_bom_product_files():
    for rel in (
        "jeeves/tests/test_fr3867_lost_ack_digest_reconcile.py",
        "jeeves/tests/test_mrb3871_hostile_lost_ack_digest.py",
        "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md",
    ):
        raw = (ROOT / rel).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), rel
        text = raw.decode("utf-8")
        assert "\x00" not in text
        assert text.endswith("\n") or text.endswith("\r\n")
