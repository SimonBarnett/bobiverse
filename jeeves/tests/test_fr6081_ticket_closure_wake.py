"""FR #6081: ticket_closure delivers closed[] via wake_bob; seen after wake or skip."""
from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from repo_layout import REPO

_MON = REPO / "jeeves" / "tools" / "monitor"
if str(_MON) not in sys.path:
    sys.path.insert(0, str(_MON))

import ticket_closure as tc  # noqa: E402
from test_fr6064_ticket_closure_dedupe import STATE, _fx, _homes


def _args(chair: Path, digest: Path) -> Namespace:
    return Namespace(
        chair_home=str(chair),
        digest_home=str(digest),
        dry_run=False,
        help_exit0=False,
    )


def _row() -> dict:
    return {
        "kind": "issue",
        "event": "closed",
        "repo": "SimonBarnett/bobiverse",
        "number": 81,
        "closed_at": "2026-11-03T15:00:00Z",
        "delivery_id": "del-81",
    }


def test_fr6081_wake_success_marks_seen(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json", [_row()])
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_FIXTURE", str(fx))
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE", "1")
    sent = []

    def send(*, agent: str, text: str):
        sent.append((agent, text))
        return {"ok": True}

    monkeypatch.setattr(tc, "_WAKE_SEND", send)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload.get("woke") == 1
    assert sent and sent[0][0] == "Bob"
    assert "SimonBarnett/bobiverse#81" in sent[0][1]
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body.get("pending") in ({}, None)
    keys = list((body.get("seen") or {}).keys())
    assert any("del-81" in k for k in keys)
    assert not (digest / "queue.json").exists()


def test_fr6081_unreachable_persists_skip_then_seen(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json", [_row()])
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_FIXTURE", str(fx))
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE", "1")

    def send(*, agent: str, text: str):
        raise ConnectionError("bob down")

    monkeypatch.setattr(tc, "_WAKE_SEND", send)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload.get("woke") == 0
    skips = digest / tc.WAKE_SKIP_NAME
    assert skips.is_file()
    blob = json.loads(skips.read_text(encoding="utf-8"))
    assert any("bob_unreachable" in json.dumps(v) for v in blob.values())
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert any("del-81" in k for k in (body.get("seen") or {}))
    payload2, code2 = tc.check(_args(chair, digest))
    assert code2 == 0
    assert payload2.get("closed") == []


def test_fr6081_no_wake_leaves_pending_not_seen(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json", [_row()])
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_FIXTURE", str(fx))
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_WAKE", raising=False)
    monkeypatch.setattr(tc, "_WAKE_SEND", lambda **k: (_ for _ in ()).throw(RuntimeError("no send")))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body.get("seen") in ({}, None)
    assert any("del-81" in k for k in (body.get("pending") or {}))
    payload2, code2 = tc.check(_args(chair, digest))
    assert code2 == 0
    assert payload2.get("closed") == []
