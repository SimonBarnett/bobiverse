"""FR #1993 WP2: jeeves.exe --self-test/--heal wire monitor libs + empty-offer wording."""
from __future__ import annotations

import io
import json
import time
from contextlib import redirect_stdout
from pathlib import Path

import gitclaim
import jeeves_main

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
MAIN = ROOT / "common/scripts/jeeves_main.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr1993_wp2_doc_marks_wp2_and_refs_only():
    text = DOC.read_text(encoding="utf-8")
    _no_bom(DOC)
    assert "WP2" in text
    assert "Refs" in text
    assert "never" in text.lower() and "Closes" in text
    assert "--heal" in text or "heal" in text
    assert "monitor" in text.lower()
    # WP2 status should no longer say only "next"
    assert "this PR" in text.lower() or "done" in text.lower() or "landed" in text.lower()
    assert text.encode("utf-8").endswith(b"\n")


def test_fr1993_wp2_cli_flags_present():
    text = MAIN.read_text(encoding="utf-8")
    assert "--heal" in text
    assert "--dry-run" in text
    assert "--force-orphan-busy" in text
    assert "--check" in text
    assert "run_heal" in text
    assert "run_monitor_check" in text or "monitor" in text.lower()


def test_fr1993_wp2_self_test_check_filter(tmp_path):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_self_test(
            home=tmp_path,
            as_json=True,
            checks=["imports", "locks"],
        )
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert payload["fr"] == 1993
    assert payload["wp"] == 2
    assert code == payload["exit"]
    assert code in (0, 1, 2)
    assert "imports" in payload.get("checks", {}) or "imports" in str(payload)
    assert "http" not in payload.get("checks", {}) or payload["checks"].get("http") is None


def test_fr1993_wp2_self_test_queue_and_offer(tmp_path):
    q = {
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "1993",
                "url": "https://github.com/SimonBarnett/bobiverse/issues/1993",
                "require_machine": "ionos",
            },
            {
                "repo": "SimonBarnett/other",
                "task": "FR",
                "id": "1",
                "url": "https://github.com/SimonBarnett/other/issues/1",
            },
        ],
        "accepted": {},
        "done": [],
    }
    (tmp_path / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    focus = {"strict": True, "repos": {"SimonBarnett/bobiverse": {"priority": 1}}, "items": {}}
    (tmp_path / "focus.json").write_text(json.dumps(focus), encoding="utf-8")

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_self_test(
            home=tmp_path,
            as_json=True,
            checks=["queue", "offer"],
            chair_home=tmp_path,
        )
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert code in (0, 1, 2)
    offer = payload.get("checks", {}).get("offer") or {}
    assert offer.get("unaccepted") == 2
    assert offer.get("out_of_focus", 0) >= 1
    assert offer.get("require_machine", 0) >= 1


def test_fr1993_wp2_heal_dry_run_stale_gitclaim_lock(tmp_path):
    lock = tmp_path / gitclaim.LOCK_NAME
    lock.write_text("stale\n", encoding="utf-8")
    # Make mtime old enough to be stale (> max(30, LOCK_WAIT_S))
    old = time.time() - max(90.0, float(getattr(gitclaim, "LOCK_WAIT_S", 30)) + 10)
    import os

    os.utime(lock, (old, old))

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_heal(
            home=tmp_path,
            dry_run=True,
            force_orphan_busy=False,
            as_json=True,
        )
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert payload["fr"] == 1993
    assert payload["wp"] == 2
    assert payload.get("dry_run") is True
    actions = payload.get("actions") or []
    assert any("git-claim.lock" in str(a) for a in actions)
    assert lock.is_file(), "dry-run must not delete the lock"
    assert code in (0, 1, 2)


def test_fr1993_wp2_heal_breaks_stale_gitclaim_lock(tmp_path):
    lock = tmp_path / gitclaim.LOCK_NAME
    lock.write_text("stale\n", encoding="utf-8")
    old = time.time() - 120
    import os

    os.utime(lock, (old, old))

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_heal(
            home=tmp_path,
            dry_run=False,
            force_orphan_busy=False,
            as_json=True,
        )
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert not lock.exists() or any("broke" in str(a).lower() for a in (payload.get("actions") or []))
    assert code in (0, 1, 2)


def test_fr1993_wp2_heal_force_orphan_requires_empty_accepted(tmp_path):
    q = {
        "unaccepted": [],
        "accepted": {
            "x": {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "1",
                "nick": "seat-1",
            }
        },
        "done": [],
    }
    (tmp_path / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_heal(
            home=tmp_path,
            dry_run=True,
            force_orphan_busy=True,
            as_json=True,
        )
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    notes = " ".join(str(x) for x in (payload.get("notes") or []) + (payload.get("actions") or []))
    assert "accepted" in notes.lower() or "orphan" in notes.lower() or "skip" in notes.lower()
    assert code in (0, 1, 2)


def test_fr1993_wp2_format_nothing_queued_with_stats():
    bare = gitclaim.format_nothing_queued("seat-1")
    assert bare == "seat-1: nothing queued"
    rich = gitclaim.format_nothing_queued(
        "seat-1",
        {
            "unaccepted": 41,
            "offerable": 0,
            "out_of_focus": 36,
            "require_machine": 3,
        },
    )
    assert "0 offerable under focus" in rich
    assert "41 unaccepted" in rich
    assert "36 out-of-focus" in rich
    assert "require_machine" in rich


def test_fr1993_wp2_summarize_empty_offer(tmp_path):
    q = {
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "1993",
                "require_machine": "ionos",
            },
            {"repo": "SimonBarnett/other", "task": "FR", "id": "2"},
        ],
        "accepted": {},
        "done": [],
    }
    (tmp_path / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    (tmp_path / "focus.json").write_text(
        json.dumps({"strict": True, "repos": {"SimonBarnett/bobiverse": {"priority": 1}}, "items": {}}),
        encoding="utf-8",
    )
    stats = gitclaim.summarize_empty_offer(tmp_path, "marchhare-1")
    assert stats["unaccepted"] == 2
    assert stats["out_of_focus"] >= 1
    assert stats["require_machine"] >= 1
    assert stats["offerable"] == 0


def test_fr1993_wp2_main_heal_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.main(["--heal", "--dry-run", "--json", "--digest-home", str(tmp_path)])
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload.get("dry_run") is True
    assert code in (0, 1, 2)


def test_fr1993_wp2_monitor_path_resolves():
    root = jeeves_main.monitor_tools_dir()
    assert root is not None
    assert (root / "health.py").is_file()
    assert (root / "_common.py").is_file()
