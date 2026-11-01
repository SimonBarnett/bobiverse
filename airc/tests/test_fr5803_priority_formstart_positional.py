"""FR #5803: PRIORITY formStart accepts bare <instance> <form> like status."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _core(auth_ops=("bob-marchhare",), machine="marchhare", **kw):
    auth = ops_auth(*auth_ops, channel=f"#{machine}")
    return ac.AircConsoleCore(
        machine=machine, auth=auth, nick=f"{machine}_console", **kw
    )


def test_fr5803_parse_positional_formstart():
    p = ap.parse_priority_walk_command("PRIORITY formStart fixture CUST")
    assert p is not None
    assert p[0] == "formStart"
    assert p[1]["instance"] == "fixture"
    assert p[1]["form"] == "CUST"


def test_fr5803_parse_mixed_positional_and_kv():
    p = ap.parse_priority_walk_command(
        "id=aabbccdd PRIORITY formStart hrs-dev-live1 form=CUST"
    )
    assert p is not None
    assert p[1]["id"] == "aabbccdd"
    assert p[1]["instance"] == "hrs-dev-live1"
    assert p[1]["form"] == "CUST"


def test_fr5803_kv_still_wins_over_positional():
    p = ap.parse_priority_walk_command(
        "PRIORITY formStart ignored CUST instance=fixture form=ORD"
    )
    assert p is not None
    assert p[1]["instance"] == "fixture"
    assert p[1]["form"] == "ORD"


def test_fr5803_positional_walk_resolves_same_id_as_status(tmp_path):
    allow = tmp_path / "priority-instances.json"
    allow.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "hrs-dev-live1",
                        "url": "https://prioritydev.example.invalid",
                        "company": "live1",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/hrs-priority-dev",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    core = _core(
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(FIX),
    )
    # Status accepts bare id (control).
    st = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "id=aabb0001 PRIORITY status hrs-dev-live1"
    )
    assert st is not None
    assert "unknown-instance" not in (st.reply or "")

    # Pre-fix wire shape from HR Smith notes: formStart <id> <form>.
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "id=aabb0002 PRIORITY formStart hrs-dev-live1 CUST"
    )
    assert r is not None
    assert r.action == "priority"
    assert "unknown-instance" not in (r.reply or "")
    assert "DONE id=aabb0002 exit=0" in (r.reply or "")
    body = json.loads(
        [ln for ln in (r.reply or "").splitlines() if ln.startswith("out ")][0].split(
            " ", 3
        )[-1]
    )
    assert body["ok"] is True
    assert body["op"] == "formStart"


def test_fr5803_skills_document_positional():
    root = Path(ap.__file__).resolve().parents[1]
    blob = (root / ".grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "5803" in blob
    assert "formStart" in blob
    assert "instance=" in blob
