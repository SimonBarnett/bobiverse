from __future__ import annotations

import json

import copilot_dispatch as cd
import focus_ignore as fi


ALLOWED = (
    "SimonBarnett/bobiverse",
    "SimonBarnett/a-search",
)


def _row(repo: str, ident: str = "#1") -> dict:
    return {"repo": repo, "task": "FR", "id": ident}


def test_default_and_explicit_high_are_restricted_to_allowed_repos(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    fi.handle_focus_cmd(tmp_path, "SimonBarnett/trutex")
    fi.handle_focus_cmd(tmp_path, "high SimonBarnett/ce-priority")
    fi.handle_focus_cmd(tmp_path, "1 SimonBarnett/other")

    doc = fi.load_focus(tmp_path)
    assert fi.DEFAULT_PRIORITY != fi.NAMED_PRIORITY["high"]
    assert fi.repo_priority(doc, "SimonBarnett/trutex") == fi.DEFAULT_PRIORITY
    assert fi.repo_priority(doc, "SimonBarnett/ce-priority") == fi.NAMED_PRIORITY["medium"]
    assert fi.repo_priority(doc, "SimonBarnett/other") == fi.NAMED_PRIORITY["medium"]
    assert not cd.is_high_priority(tmp_path, _row("SimonBarnett/trutex"))
    assert not cd.is_high_priority(tmp_path, _row("SimonBarnett/ce-priority"))

    for repo in ALLOWED:
        fi.handle_focus_cmd(tmp_path, f"high {repo}")
        focused = fi.load_focus(tmp_path)
        assert fi.repo_priority(focused, repo) == fi.NAMED_PRIORITY["high"]
        assert cd.is_high_priority(tmp_path, _row(repo))


def test_loaded_legacy_or_invalid_focus_cannot_make_other_repo_high(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    path = fi._root(tmp_path) / fi.FOCUS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = (
        ({"repos": {"SimonBarnett/trutex": {"label": "high"}}}, fi.DEFAULT_PRIORITY),
        (
            {"repos": {"SimonBarnett/trutex": {"priority": "invalid", "label": "high"}}},
            fi.DEFAULT_PRIORITY,
        ),
        (
            {"repos": {"SimonBarnett/trutex": {"priority": 1, "label": "high"}}},
            fi.NAMED_PRIORITY["medium"],
        ),
        ({"repos": ["SimonBarnett/trutex"]}, fi.NAMED_PRIORITY["medium"]),
    )
    for raw, expected_priority in cases:
        path.write_text(json.dumps(raw), encoding="utf-8")
        doc = fi.load_focus(tmp_path)
        assert doc["repos"]
        assert fi.repo_priority(doc, "SimonBarnett/trutex") == expected_priority
        assert fi._repo_entry(doc, "SimonBarnett/trutex")[0] == expected_priority
        assert fi.offer_sort_key(tmp_path, _row("SimonBarnett/trutex"))[1] == expected_priority
        assert not cd.is_high_priority(tmp_path, _row("SimonBarnett/trutex"))

    for raw, expected_repo in (
        ({"repos": {"SimonBarnett/bobiverse": {"priority": 1}}}, ALLOWED[0]),
        ({"repos": ["SimonBarnett/a-search"]}, ALLOWED[1]),
    ):
        path.write_text(json.dumps(raw), encoding="utf-8")
        doc = fi.load_focus(tmp_path)
        assert doc["repos"]
        assert fi.repo_priority(doc, expected_repo) == fi.NAMED_PRIORITY["high"]
        assert cd.is_high_priority(tmp_path, _row(expected_repo))


def test_item_focus_cannot_bypass_repository_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    fi.handle_focus_cmd(tmp_path, "SimonBarnett/a-search#5058")
    fi.handle_focus_cmd(tmp_path, "SimonBarnett/ce-priority#39")
    fi.handle_focus_cmd(tmp_path, "SimonBarnett/trutex#33")

    assert fi.offer_sort_key(tmp_path, _row("SimonBarnett/a-search", "#5058"))[1] == 1
    assert fi.offer_sort_key(tmp_path, _row("SimonBarnett/ce-priority", "#39"))[1] == 2
    assert fi.offer_sort_key(tmp_path, _row("SimonBarnett/trutex", "#33"))[1] == 3
    assert not cd.is_high_priority(tmp_path, _row("SimonBarnett/ce-priority", "#39"))
    assert not cd.is_high_priority(tmp_path, _row("SimonBarnett/trutex", "#33"))
    assert cd.is_high_priority(tmp_path, _row("SimonBarnett/a-search", "#5058"))
