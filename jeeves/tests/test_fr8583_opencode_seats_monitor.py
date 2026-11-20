"""FR #8583: opencode_seats monitor uses live /report for flamingo OpenCode."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import opencode_seats as oc  # noqa: E402


def _fixture(**kwargs):
    base = {
        "machines": {
            "flamingo": {
                "workers": {
                    "16764": {
                        "nick": "flamingo-16764",
                        "state": "doing",
                        "kind": "opencode",
                        "start_model": "opencode-go/deepseek-v4-pro",
                        "updated": "2026-11-20T22:12:00Z",
                        "work": "MRB SimonBarnett/bobiverse#8549",
                        "model_mismatch": False,
                    },
                    "4336": {
                        "nick": "flamingo-4336",
                        "state": "doing",
                        "kind": "opencode",
                        "start_model": "opencode-go/deepseek-v4-pro",
                        "updated": "2026-11-20T22:45:00Z",
                        "work": "FR SimonBarnett/bobiverse#8578",
                        "model_mismatch": False,
                    },
                }
            },
            "redqueen": {
                "workers": {
                    "1": {
                        "nick": "redqueen-1",
                        "state": "doing",
                        "kind": "grok",
                        "start_model": "grok",
                        "updated": "2026-11-20T20:00:00Z",
                        "work": "FR x",
                    }
                }
            },
        },
        "opencode": {
            "windows": {
                "week": {
                    "status": "exhausted",
                    "used_pct": 100,
                    "remaining_pct": 0,
                    "limited": True,
                    "reset_label": "2d 1h",
                },
                "rolling": {
                    "status": "known",
                    "used_pct": 33,
                    "remaining_pct": 67,
                    "limited": False,
                },
            }
        },
    }
    base.update(kwargs)
    return base


class _Resp:
    def __init__(self, body: dict):
        self._raw = json.dumps(body).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_age_sec_iso():
    from datetime import datetime, timezone

    updated = datetime(2026, 11, 20, 22, 12, 0, tzinfo=timezone.utc).timestamp()
    age = oc._age_sec("2026-11-20T22:12:00Z", now=updated + 1989)
    assert age is not None
    assert abs(age - 1989) < 2


def test_finding_stuck_age_and_week_exhausted(monkeypatch, tmp_path: Path):
    doc = _fixture()
    fix = tmp_path / "report.json"
    fix.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("BOB_OPENCODE_SEATS_FIXTURE", str(fix))
    monkeypatch.setenv("BOB_OPENCODE_STUCK_AGE_SEC", "900")
    monkeypatch.delenv("BOB_REPORT_URL", raising=False)
    # now = updated(16764)+1989
    now = 1763673120.0 + 1989
    # Recompute: parse updated of 16764
    from datetime import datetime, timezone

    updated = datetime.fromisoformat("2026-11-20T22:12:00+00:00").timestamp()
    now = updated + 1989
    args = SimpleNamespace(chair_home="", digest_home="", dry_run=False)
    payload, code = oc.check(args, now=now)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["opencode_worker_count"] == 2
    assert any("flamingo-16764" in f and "age_sec" in f for f in payload["findings"])
    assert any("week exhausted" in f for f in payload["findings"])
    assert payload["windows"]["week_limited"] is True
    # redqueen grok seat ignored
    assert all(s["nick"].startswith("flamingo-") for s in payload["seats"])


def test_ok_when_fresh_and_week_ok(monkeypatch, tmp_path: Path):
    doc = _fixture(
        opencode={
            "windows": {
                "week": {
                    "status": "known",
                    "used_pct": 10,
                    "remaining_pct": 90,
                    "limited": False,
                },
                "rolling": {"status": "known", "limited": False, "remaining_pct": 80},
            }
        }
    )
    # freshen updates
    for w in doc["machines"]["flamingo"]["workers"].values():
        w["updated"] = "2026-11-20T22:50:00Z"
        w["state"] = "idle"
        w["work"] = ""
    fix = tmp_path / "report.json"
    fix.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("BOB_OPENCODE_SEATS_FIXTURE", str(fix))
    args = SimpleNamespace(chair_home="", digest_home="", dry_run=False)
    from datetime import datetime

    now = datetime.fromisoformat("2026-11-20T22:51:00+00:00").timestamp()
    payload, code = oc.check(args, now=now)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["findings"] == []


def test_fetch_report_uses_user_agent(monkeypatch):
    seen = {}

    def opener(req, timeout=30.0):
        seen["ua"] = req.get_header("User-agent") or req.headers.get("User-agent")
        return _Resp(_fixture())

    doc = oc.fetch_report("https://example.test/bob/v1/report", opener=opener)
    assert "machines" in doc
    assert "BobiverseJeevesMonitor" in (seen.get("ua") or "")


def test_dry_run_exit0():
    import subprocess

    r = subprocess.run(
        [sys.executable, str(MON / "opencode_seats.py"), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MON),
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["dry_run"] is True
