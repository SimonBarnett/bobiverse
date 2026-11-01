"""Hostile pins for MRB #5806 / FR #5803 PRIORITY formStart positional args."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _core(tmp_path, allow_id="hrs-dev-live1"):
    allow = tmp_path / "priority-instances.json"
    allow.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": allow_id,
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
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(FIX),
    )


def test_mrb5806_one_positional_is_missing_form_not_unknown(tmp_path):
    """Bare formStart <id> without form must not look like unknown-instance."""
    core = _core(tmp_path)
    r = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "id=aabb5806 PRIORITY formStart hrs-dev-live1"
    )
    assert r is not None
    text = r.reply or ""
    assert "unknown-instance" not in text
    assert "missing-form" in text


def test_mrb5806_subform_and_getrows_positionals():
    sub = ap.parse_priority_walk_command("PRIORITY subform hrs-dev-live1 CUST /x")
    assert sub is not None
    assert sub[0] == "subform"
    assert sub[1]["instance"] == "hrs-dev-live1"
    assert sub[1]["form"] == "CUST"
    assert sub[1]["path"] == "/x"
    gr = ap.parse_priority_walk_command("PRIORITY getRows hrs-dev-live1 CUST")
    assert gr is not None
    assert gr[1]["instance"] == "hrs-dev-live1"
    assert gr[1]["form"] == "CUST"


def test_mrb5806_skill_keeps_both_cred_persist_and_formstart_pins():
    root = Path(ap.__file__).resolve().parents[1]
    blob = (root / ".grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "<<<<<<<" not in blob
    assert "CRED persist" in blob and "via=https" in blob
    assert "Form walk (FR #5285 / #5803 / #5837)" in blob
    assert "PRIORITY formStart example-dev CUST" in blob
    assert "PRIORITY formStart instance=example-dev form=CUST" in blob
