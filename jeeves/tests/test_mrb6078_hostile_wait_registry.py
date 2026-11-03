"""MRB #6078 hostile extras: env registry path + 6064 de-dupe still holds."""
from __future__ import annotations

import json
from pathlib import Path

from test_fr6064_ticket_closure_dedupe import STATE, _fx as _fx64, _homes, _run
from test_fr6069_ticket_closure_wait_registry import REGISTRY, _fx


def test_mrb6078_env_waiting_overrides_digest(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json")
    (digest / REGISTRY).write_text(
        json.dumps({"waiting_on": ["SimonBarnett/bobiverse#11"]}),
        encoding="utf-8",
    )
    alt = tmp_path / "wait-env.json"
    alt.write_text(
        json.dumps({"waiting_on": ["SimonBarnett/bobiverse#12"]}),
        encoding="utf-8",
    )
    code, payload = _run(
        chair,
        digest,
        {
            "JEEVES_TICKET_CLOSURE_FIXTURE": str(fx),
            "JEEVES_TICKET_CLOSURE_WAITING": str(alt),
        },
    )
    assert code == 1, payload
    assert [c["number"] for c in payload.get("closed") or []] == [12]


def test_mrb6078_waiting_plus_dedupe_same_delivery(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    first = {
        "kind": "issue",
        "event": "closed",
        "repo": "SimonBarnett/bobiverse",
        "number": 11,
        "closed_at": "2026-11-03T14:00:00Z",
        "delivery_id": "del-11",
    }
    (digest / REGISTRY).write_text(
        json.dumps({"waiting_on": ["SimonBarnett/bobiverse#11"]}),
        encoding="utf-8",
    )
    fx = _fx64(tmp_path / "events.json", [first])
    env = {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)}
    c1, p1 = _run(chair, digest, env)
    assert c1 == 1, p1
    c2, p2 = _run(chair, digest, env)
    assert c2 == 0, p2
    assert (digest / STATE).is_file()
