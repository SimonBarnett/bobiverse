"""FR #9880: 9830_harvest / lessons_digest_harvest checklist + helper."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
SCRIPTS = REPO / "jeeves" / "scripts"
START = REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
MONITOR_SKILL = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
FR_DIGEST = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-digest" / "SKILL.md"
AGENTS = REPO / "jeeves" / "AGENTS.md"
INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"

sys.path.insert(0, str(MONITOR))
import lessons_digest_harvest as ldh  # noqa: E402


def _run(script: str, env: dict | None = None) -> tuple[int, dict]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    # Avoid leaking live tokens into fixture mode unexpectedly when we only want fixture.
    proc = subprocess.run(
        [sys.executable, str(MONITOR / script)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR),
        env=full_env,
    )
    lines = (proc.stdout or "").strip().splitlines()
    assert lines, (proc.returncode, proc.stdout, proc.stderr)
    return proc.returncode, json.loads(lines[-1])


def test_parse_digest_spec_and_env_override(monkeypatch):
    assert ldh.parse_digest_spec("9830") == ("SimonBarnett/bobiverse", 9830)
    assert ldh.parse_digest_spec("#42") == ("SimonBarnett/bobiverse", 42)
    assert ldh.parse_digest_spec("acme/x#7") == ("acme/x", 7)
    monkeypatch.setenv("JEEVES_LESSONS_DIGEST", "acme/bob#100")
    assert ldh.env_digest_override() == ("acme/bob", 100)


def test_pick_active_prefers_lessons_cue_over_unrelated_held(tmp_path: Path):
    issues = [
        {
            "number": 10,
            "repo": "SimonBarnett/bobiverse",
            "state": "OPEN",
            "labels": ["fr-digest", "hold"],
            "title": "Digest: unrelated pack",
            "body": "no cues",
        },
        {
            "number": 9830,
            "repo": "SimonBarnett/bobiverse",
            "state": "OPEN",
            "labels": ["fr-digest", "hold", "digest"],
            "title": "Digest: Jeeves IRCD deterministic lessons",
            "body": "CAST IRON every monitor run files new lessons here",
        },
    ]
    picked = ldh.pick_active_held_lessons_digest(issues, override=None, default=("SimonBarnett/bobiverse", 9830))
    assert picked is not None
    assert picked["number"] == 9830


def test_fixture_unfiled_finding_exits_1(tmp_path: Path, monkeypatch):
    fixture = {
        "digest": {
            "number": 9830,
            "repo": "SimonBarnett/bobiverse",
            "state": "OPEN",
            "labels": ["fr-digest", "hold"],
            "title": "Digest: Jeeves IRCD deterministic lessons",
            "body": "lessons harvest",
        },
        "children": [
            {
                "number": 9881,
                "state": "OPEN",
                "title": "already filed twin",
                "body": "Depends-on: #9830\n",
            }
        ],
        "session_findings": [
            {"title": "NSSM twin bob-ear spawn", "fingerprint": "nssm-twin-ear"},
        ],
    }
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    code, payload = _run(
        "9830_harvest.py",
        {"JEEVES_LESSONS_DIGEST_FIXTURE": str(path)},
    )
    assert code == 1
    assert payload["checklist"] == "9830_harvest"
    assert payload["active_digest"]["number"] == 9830
    assert payload["unfiled"]
    assert payload["ok"] is False


def test_fixture_covered_finding_exits_0(tmp_path: Path, monkeypatch):
    fixture = {
        "digest": {
            "number": 9830,
            "repo": "SimonBarnett/bobiverse",
            "state": "OPEN",
            "labels": ["fr-digest", "hold"],
            "title": "Digest: Jeeves IRCD lessons",
            "body": "IRCD lessons",
        },
        "children": [
            {
                "number": 9861,
                "state": "OPEN",
                "title": "NSSM twin bob-ear spawn",
                "body": "Depends-on: #9830\n",
            }
        ],
        "session_findings": [
            {"title": "NSSM twin bob-ear spawn", "fingerprint": "nssm-twin-ear"},
        ],
    }
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    code, payload = _run(
        "lessons_digest_harvest.py",
        {"JEEVES_LESSONS_DIGEST_FIXTURE": str(path)},
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["children_count"] == 1
    assert not payload["unfiled"]


def test_no_active_held_digest_soft_ok(tmp_path: Path, monkeypatch):
    fixture = {
        "digest": {
            "number": 9830,
            "repo": "SimonBarnett/bobiverse",
            "state": "CLOSED",
            "labels": ["fr-digest", "hold"],
            "title": "Digest: Jeeves IRCD lessons",
            "body": "lessons",
        },
        "children": [],
        "session_findings": [{"title": "x"}],
    }
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    code, payload = _run(
        "9830_harvest.py",
        {"JEEVES_LESSONS_DIGEST_FIXTURE": str(path)},
    )
    assert code == 0
    assert payload.get("soft_ok") == "no_active_held_lessons_digest"


def test_dry_run_both_names():
    for name in ("9830_harvest.py", "lessons_digest_harvest.py"):
        code, payload = _run(name, None)
        # without dry-run flag this may soft-ok no token; use explicit dry-run
        proc = subprocess.run(
            [sys.executable, str(MONITOR / name), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(MONITOR),
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload["ok"] is True
        assert payload["dry_run"] is True


def test_skills_and_agents_list_checklist():
    start = START.read_text(encoding="utf-8")
    assert "9830_harvest" in start
    assert "FR #9880" in start
    assert "JEEVES_LESSONS_DIGEST" in start
    mon = MONITOR_SKILL.read_text(encoding="utf-8")
    assert "FR #9880" in mon
    assert "9830_harvest" in mon
    frd = FR_DIGEST.read_text(encoding="utf-8")
    assert "FR #9880" in frd
    agents = AGENTS.read_text(encoding="utf-8")
    assert "9830_harvest" in agents
    assert "FR #9880" in agents


def test_invoke_validateset_and_wrappers_exist():
    inv = INVOKE.read_text(encoding="utf-8")
    assert "9830_harvest" in inv
    assert "lessons_digest_harvest" in inv
    assert (MONITOR / "9830_harvest.py").is_file()
    assert (MONITOR / "lessons_digest_harvest.py").is_file()
    assert (SCRIPTS / "Test-JeevesMonitor9830Harvest.ps1").is_file()
    assert (SCRIPTS / "Test-JeevesMonitorLessonsDigestHarvest.ps1").is_file()
    assert (SCRIPTS / "Compare-JeevesLessonsDigestFindings.ps1").is_file()


def test_default_not_forever_hardcoded_only_path():
    """Documented default exists, but detection/env paths are first-class."""
    src = (MONITOR / "lessons_digest_harvest.py").read_text(encoding="utf-8")
    assert "DEFAULT_DIGEST_NUMBER = 9830" in src
    assert "JEEVES_LESSONS_DIGEST" in src
    assert "pick_active_held_lessons_digest" in src
    assert "Do **not** hardcode forever" in src or "Do not hardcode forever" in src
