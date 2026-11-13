"""FR #7121: agentic_fomprep alias of SimonBarnett/priority-mcp."""
from __future__ import annotations

import json
from pathlib import Path

import gitclaim
import intake
import repo_alias
from gitclaim import GitClaim, apply_queue_event, load_queue, load_unaccepted
from repo_alias import PRIORITY_MCP_ALIAS, PRIORITY_MCP_CANONICAL


def test_canonicalize_either_name():
    assert repo_alias.canonicalize_repo(PRIORITY_MCP_ALIAS) == PRIORITY_MCP_CANONICAL
    assert repo_alias.canonicalize_repo("simonbarnett/agentic_fomprep") == PRIORITY_MCP_CANONICAL
    assert repo_alias.canonicalize_repo(PRIORITY_MCP_CANONICAL) == PRIORITY_MCP_CANONICAL
    assert repo_alias.repos_equivalent(PRIORITY_MCP_ALIAS, PRIORITY_MCP_CANONICAL)


def test_claim_from_either_full_name_same_queue_row(tmp_path: Path):
    apply_queue_event(
        tmp_path,
        GitClaim(
            repo=PRIORITY_MCP_ALIAS,
            task="FR",
            id="#1",
            event="issues",
            action="opened",
            line="",
            title="x",
            state="open",
        ),
    )
    st = apply_queue_event(
        tmp_path,
        GitClaim(
            repo=PRIORITY_MCP_CANONICAL,
            task="FR",
            id="#1",
            event="issues",
            action="opened",
            line="",
            title="x",
            state="open",
        ),
    )
    assert st == "duplicate"
    rows = load_unaccepted(tmp_path)
    assert len(rows) == 1
    assert rows[0]["repo"] == PRIORITY_MCP_CANONICAL


def test_intake_alias_files_canonical():
    assert intake.repo_allowed(PRIORITY_MCP_ALIAS)
    assert intake.repo_allowed(PRIORITY_MCP_CANONICAL)
    owner = intake.lesson_owner_repo(title="priority catalog CAT-T1 formprep")
    assert owner.repo == PRIORITY_MCP_CANONICAL


def test_queue_old_name_survives_reload(tmp_path: Path):
    path = gitclaim.queue_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": PRIORITY_MCP_ALIAS,
                        "task": "FR",
                        "id": "#99",
                        "ts": "",
                        "line": "",
                        "event": "issues",
                        "action": "opened",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    doc = load_queue(tmp_path)
    rows = doc["unaccepted"]
    assert rows[0]["repo"] == PRIORITY_MCP_CANONICAL
    bak = path.with_name(path.name + ".bak-fr7121")
    assert bak.is_file()
    again = load_queue(tmp_path)
    assert again["unaccepted"][0]["repo"] == PRIORITY_MCP_CANONICAL


def test_ledger_keys_migrate_old_name(tmp_path: Path):
    p = gitclaim.ledger_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "v": 1,
                "touch": {},
                "giveup": {f"{PRIORITY_MCP_ALIAS.lower()}#11": {"seat": ["FR"]}},
                "fr_done": {},
                "mrb_done": {},
            }
        ),
        encoding="utf-8",
    )
    led = gitclaim.ledger_load(tmp_path)
    assert f"{PRIORITY_MCP_CANONICAL.lower()}#11" in led["giveup"]
    assert gitclaim._lkey(PRIORITY_MCP_ALIAS, "#11") == f"{PRIORITY_MCP_CANONICAL.lower()}#11"


def test_canonical_queue_repo_not_archived():
    assert gitclaim.canonical_queue_repo(PRIORITY_MCP_ALIAS) == PRIORITY_MCP_CANONICAL
    assert gitclaim.repo_archived_for_queue(PRIORITY_MCP_ALIAS) is False
    assert gitclaim.canonical_queue_repo("SimonBarnett/bobiverse") == "SimonBarnett/bobiverse"
