"""FR #1043: monitor ops home falls back to digest; auto_focus counts dict repos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import _common  # noqa: E402
import auto_focus  # noqa: E402
import health  # noqa: E402
import queue_flow  # noqa: E402


def test_ops_home_falls_back_to_digest_when_chair_queue_missing(tmp_path):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [{"repo": "o/a", "task": "FR", "id": "#1"}], "accepted": []}),
        encoding="utf-8",
    )
    assert _common.ops_home(chair, digest) == digest
    assert _common.resolve_queue_path(chair, digest) == digest / "queue.json"
    # chair wins when it has the file
    (chair / "queue.json").write_text("{}", encoding="utf-8")
    assert _common.ops_home(chair, digest) == chair


def test_chair_focus_only_does_not_hide_digest_queue(tmp_path):
    """MRB #1234: lone focus.json on ~/.jeeves must not poison queue resolve."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps({"strict": True, "repos": {"SimonBarnett/bobiverse": {}}}),
        encoding="utf-8",
    )
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [{"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#1"}],
                "accepted": [],
            }
        ),
        encoding="utf-8",
    )
    assert _common.resolve_queue_path(chair, digest) == digest / "queue.json"
    assert _common.resolve_focus_path(chair, digest) == chair / "focus.json"
    assert _common.ops_home(chair, digest) == digest
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest)})()
    payload, code = queue_flow.check(args)
    assert code == 0, payload
    assert payload.get("ok") is True


def test_queue_flow_uses_digest_fallback(tmp_path, monkeypatch):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#9",
                        "labels": ["feature-request"],
                        "title": "FR: x",
                        "line": "FR SimonBarnett/bobiverse#9",
                    }
                ],
                "accepted": [],
            }
        ),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest)})()
    payload, code = queue_flow.check(args)
    assert code == 0
    assert payload.get("ok") is True
    assert payload.get("ops_home") == str(digest) or "bobiverse" in str(payload.get("queue_path", ""))


def test_auto_focus_counts_dict_repos(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "focus.json").write_text(
        json.dumps(
            {
                "strict": True,
                "repos": {
                    "SimonBarnett/bobiverse": {},
                    "SimonBarnett/xai-cookbook": {},
                    "SimonBarnett/agentic_fomprep": {},
                },
            }
        ),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest)})()
    payload, code = auto_focus.check(args)
    assert code == 0
    assert payload["ok"] is True
    assert payload["repo_count"] == 3
    assert payload["strict"] is True


def test_auto_focus_strict_empty_dict_still_finds(tmp_path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "focus.json").write_text(
        json.dumps({"strict": True, "repos": {}}),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest)})()
    payload, code = auto_focus.check(args)
    assert code == 1
    assert payload["ok"] is False
    assert payload["repo_count"] == 0


def test_health_bobcallback_accepts_scheduled_task(monkeypatch):
    calls = []

    def fake_service(name: str) -> str:
        calls.append(("svc", name))
        if name == "BobCallback":
            return "missing"
        return "Running"

    def fake_task(name: str) -> str:
        calls.append(("task", name))
        return "Running"

    def fake_port(port: int) -> bool:
        calls.append(("port", port))
        return True

    monkeypatch.setattr(health, "_service_state", fake_service)
    monkeypatch.setattr(health, "_scheduled_task_state", fake_task)
    monkeypatch.setattr(health, "_port_listening", fake_port)
    args = type("A", (), {"chair_home": str(Path.cwd()), "digest_home": str(Path.cwd())})()
    payload, code = health.check(args)
    assert code == 0
    assert payload["ok"] is True
    assert payload["services"]["BobCallback"] in ("Running", "task:Running", "listen:7700")
