"""FR #8848 / #9193: token-free depends_on monitor (offer while depend OPEN)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
START = REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"

_VIOLATING_QUEUE = {
    "v": 1,
    "unaccepted": [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#9",
            "number": 9,
            "body": "Depends-on: (none)\n",
        },
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#10",
            "number": 10,
            "offered_to": "marchhare-1",
            "body": "Depends-on: #9\n",
        },
    ],
    "accepted": [],
    "done": [],
}


def _run(
    chair: Path | None,
    digest: Path | None,
    extra: list[str] | None = None,
    *,
    script: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, dict]:
    mon = script if script is not None else (MONITOR / "depends_on.py")
    argv = [sys.executable, str(mon), *(extra or [])]
    if chair is not None:
        argv += ["--chair-home", str(chair), "--digest-home", str(digest)]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(mon.parent),
        env=env,
    )
    line = (proc.stdout or "").strip().splitlines()[-1]
    return proc.returncode, json.loads(line)


def _queue(tmp: Path, doc: dict) -> tuple[Path, Path]:
    chair = tmp / "chair"
    digest = tmp / "digest"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(json.dumps(doc), encoding="utf-8")
    return chair, digest


def _assert_no_ancestor_gitclaim(root: Path) -> None:
    """Copied readiness trees must not walk into a real repo gitclaim.py."""
    cur = root.resolve()
    for _ in range(16):
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
        marker = cur / "common" / "scripts" / "gitclaim.py"
        assert not marker.is_file(), f"ancestor gitclaim masks stub: {marker}"


def _readiness_tree(
    tmp_path: Path,
    *,
    with_parse_file: bool = False,
    gitclaim_text: str = "# stub gitclaim without bob_d3_skip_open\n",
) -> tuple[Path, Path]:
    """Copy monitor into an isolated root + profile with a violating queue.

    SKILL.md (depends-on book): live runs stay soft-ok until either
    ``depends_on_parse.py`` exists or ``gitclaim.py`` contains ``bob_d3_skip_open``.
    """
    root = tmp_path / "root"
    mon_dst = root / "jeeves" / "tools" / "monitor"
    mon_dst.mkdir(parents=True)
    shutil.copy2(MONITOR / "depends_on.py", mon_dst / "depends_on.py")
    shutil.copy2(MONITOR / "_common.py", mon_dst / "_common.py")
    scripts = root / "common" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "gitclaim.py").write_text(gitclaim_text, encoding="utf-8")
    if with_parse_file:
        (scripts / "depends_on_parse.py").write_text(
            '"""FR #8806 readiness marker stub."""\n',
            encoding="utf-8",
        )
    _assert_no_ancestor_gitclaim(root)

    profile = tmp_path / "profile"
    jeeves = profile / ".jeeves"
    bobiverse = profile / ".bobiverse"
    jeeves.mkdir(parents=True)
    bobiverse.mkdir(parents=True)
    (jeeves / "queue.json").write_text(json.dumps(_VIOLATING_QUEUE), encoding="utf-8")

    child_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "JEEVES_HOME",
            "BOB_JEEVES_HOME",
            "BOB_DIGEST_HOME",
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTHONSAFEPATH",
        }
    }
    child_env["USERPROFILE"] = str(profile)
    child_env["HOME"] = str(profile)
    return mon_dst / "depends_on.py", child_env


def test_offered_while_depend_open_exits_1(tmp_path: Path):
    chair, digest = _queue(tmp_path, _VIOLATING_QUEUE)
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["ok"] is False
    assert payload["violations"][0]["open"] == ["SimonBarnett/bobiverse#9"]


def test_skipped_with_depends_open_exits_0(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#9",
                    "number": 9,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "offered_to": "marchhare-1",
                    "status": "skipped",
                    "body": "Depends-on: #9\n",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["ok"] is True
    assert payload["violations"] == []


def test_no_depends_rows_soft_ok(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#3",
                    "labels": ["hold"],
                    "offered_to": "marchhare-1",
                    "body": "HOLD: waiting on a human\n",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["soft_ok"] == "no_depends_on_rows"


def test_closed_depend_in_done_is_ok(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "offered_to": "marchhare-1",
                    "body": "Depends-on: #9\n",
                }
            ],
            "accepted": [],
            "done": [
                {"repo": "SimonBarnett/bobiverse", "id": "#9", "number": 9},
            ],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["ok"] is True


@pytest.mark.parametrize(
    "case,with_parse,gitclaim,want_code,want_soft,want_ok",
    [
        ("no_marker", False, "# stub\n", 0, "product_not_on_tip", True),
        ("parse_marker", True, "# stub\n", 1, "", False),
        (
            "bob_d3_marker",
            False,
            "# stub\ndef bob_d3_skip_open():\n    return True\n",
            1,
            "",
            False,
        ),
    ],
)
def test_readiness_matrix_soft_ok_until_marker(
    tmp_path: Path,
    case: str,
    with_parse: bool,
    gitclaim: str,
    want_code: int,
    want_soft: str,
    want_ok: bool,
):
    """Hermetic readiness (FR #9193). Soft-ok only until either marker exists.

    Replaces the non-hermetic live-home assert that expected product_not_on_tip
    after FR #8806 already shipped depends_on_parse.py on tip (SKILL.md either-
    marker contract).
    """
    script, env = _readiness_tree(
        tmp_path, with_parse_file=with_parse, gitclaim_text=gitclaim
    )
    # Live gate: no --chair-home / --dry-run.
    code, payload = _run(None, None, script=script, env=env)
    assert code == want_code, (case, payload)
    assert payload["ok"] is want_ok, (case, payload)
    assert payload.get("soft_ok", "") == want_soft, (case, payload)
    if want_code == 0:
        assert payload["findings"] == []
        assert payload["violations"] == []
    else:
        assert payload["violations"][0]["open"] == ["SimonBarnett/bobiverse#9"]


def test_bold_depends_on_label_exits_1(tmp_path: Path):
    """FR #9193: **Depends-on:** must parse like the shared #8805 grammar."""
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#9",
                    "number": 9,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "offered_to": "marchhare-1",
                    "body": "**Depends-on:** #9\n",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["violations"][0]["open"] == ["SimonBarnett/bobiverse#9"]


def test_own_repo_relative_resolves_positive(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {"repo": "SimonBarnett/a-search", "task": "FR", "id": "#3", "number": 3},
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#4",
                    "number": 4,
                    "offered_to": "seat-1",
                    "body": "Depends-on: #3\n",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["violations"][0]["open"] == ["SimonBarnett/a-search#3"]


def test_own_repo_relative_closed_is_ok(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#4",
                    "number": 4,
                    "offered_to": "seat-1",
                    "body": "Depends-on: #3\n",
                }
            ],
            "accepted": [],
            "done": [{"repo": "SimonBarnett/a-search", "id": "#3", "number": 3}],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["ok"] is True


def test_qualified_cross_repo_retained(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/other",
                    "task": "FR",
                    "id": "#9",
                    "number": 9,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "offered_to": "seat-1",
                    "body": "Depends-on: SimonBarnett/other#9\n",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["violations"][0]["open"] == ["SimonBarnett/other#9"]
    assert payload["violations"][0]["row"] == "SimonBarnett/bobiverse#10"


def test_accepted_bucket_while_depend_open_exits_1(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#9", "number": 9},
            ],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "body": "Depends-on: #9\n",
                }
            ],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["violations"][0]["bucket"] == "accepted"
    assert payload["violations"][0]["open"] == ["SimonBarnett/bobiverse#9"]


def test_monitor_start_lists_depends_on():
    text = START.read_text(encoding="utf-8")
    assert "`depends_on`" in text
    invoke = INVOKE.read_text(encoding="utf-8")
    assert "depends_on" in invoke
    assert (REPO / "jeeves" / "scripts" / "Test-JeevesMonitorDependsOn.ps1").is_file()
    skill = (
        REPO
        / "jeeves"
        / ".grok"
        / "skills"
        / "bobiverse-jeeves-agent-depends-on"
        / "SKILL.md"
    )
    assert skill.is_file()
    assert "depends_on" in skill.read_text(encoding="utf-8")
