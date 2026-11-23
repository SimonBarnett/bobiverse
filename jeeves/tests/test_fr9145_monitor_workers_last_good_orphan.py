"""FR #9145: workers_last_good_orphan monitor check (token-free, local digest only)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tools" / "monitor" / "workers_last_good_orphan.py"
WRAPPER = ROOT / "scripts" / "Test-JeevesMonitorWorkersLastGoodOrphan.ps1"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(digest_home: Path, env: dict | None = None) -> tuple[int, dict]:
    e = os.environ.copy()
    e.pop("GITHUB_TOKEN", None)
    e.pop("GH_TOKEN", None)
    if env:
        e.update(env)
    e["BOB_DIGEST_HOME"] = str(digest_home)
    # Keep chair home out of the way.
    e["JEEVES_HOME"] = str(digest_home / "_jeeves")
    proc = subprocess.run(
        [sys.executable, str(CHECK), "--digest-home", str(digest_home)],
        capture_output=True,
        text=True,
        env=e,
        cwd=str(CHECK.parent),
    )
    line = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else "{}"
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        payload = {"_raw": proc.stdout, "_err": proc.stderr}
    return proc.returncode, payload


def test_orphan_finding(tmp_path):
    digest = tmp_path / "dig"
    digest.mkdir()
    now = datetime.now(timezone.utc)
    doc = {
        "ts": _iso(now),
        "machines": {
            "redqueen": {
                "online": True,
                "workers": {},
                "worker_list": [],
                "workers_stale": True,
                "workers_last_good": [
                    {"nick": "redqueen-1824", "state": "out_of_fuel", "work": "out-of-fuel"}
                ],
                "workers_last_good_at": _iso(now - timedelta(hours=2)),
            }
        },
    }
    (digest / "digest.json").write_text(json.dumps(doc), encoding="utf-8")
    code, payload = _run(digest)
    assert code == 1
    assert payload.get("ok") is False
    assert payload.get("findings")
    assert payload.get("orphans")
    assert payload["orphans"][0]["machine"] == "redqueen"
    assert "redqueen-1824" in payload["orphans"][0]["nicks"]
    assert "worker-remove" in (payload.get("remediation") or "")


def test_non_empty_restored_stale_list_not_orphan(tmp_path):
    digest = tmp_path / "dig"
    digest.mkdir()
    now = datetime.now(timezone.utc)
    doc = {
        "machines": {
            "redqueen": {
                "workers_stale": True,
                "workers": {},
                "worker_list": [
                    {"nick": "redqueen-1", "state": "idle", "work": "", "updated": _iso(now)}
                ],
                "workers_last_good": [
                    {"nick": "redqueen-1", "state": "idle", "work": "", "updated": _iso(now)}
                ],
                "workers_last_good_at": _iso(now),
            }
        }
    }
    (digest / "digest.json").write_text(json.dumps(doc), encoding="utf-8")
    code, payload = _run(digest)
    assert code == 0
    assert payload.get("ok") is True
    assert payload.get("orphans") == []


def test_fresh_live_list_ok(tmp_path):
    digest = tmp_path / "dig"
    digest.mkdir()
    now = datetime.now(timezone.utc)
    doc = {
        "machines": {
            "marchhare": {
                "workers_stale": False,
                "worker_list": [
                    {"nick": "marchhare-1", "state": "idle", "work": "", "updated": _iso(now)}
                ],
                "workers": {"1": {"nick": "marchhare-1"}},
            }
        }
    }
    (digest / "digest.json").write_text(json.dumps(doc), encoding="utf-8")
    code, payload = _run(digest)
    assert code == 0
    assert payload.get("ok") is True


def test_empty_snapshot_ok(tmp_path):
    digest = tmp_path / "dig"
    digest.mkdir()
    doc = {
        "machines": {
            "redqueen": {
                "workers_stale": True,
                "workers": {},
                "worker_list": [],
                "workers_last_good": [],
            }
        }
    }
    (digest / "digest.json").write_text(json.dumps(doc), encoding="utf-8")
    code, payload = _run(digest)
    assert code == 0
    assert payload.get("ok") is True


def test_missing_digest_ok(tmp_path):
    digest = tmp_path / "empty"
    digest.mkdir()
    code, payload = _run(digest)
    assert code == 0
    assert payload.get("digest_present") is False
    assert payload.get("ok") is True


def test_malformed_json_exit2(tmp_path):
    digest = tmp_path / "dig"
    digest.mkdir()
    (digest / "digest.json").write_text("{not-json", encoding="utf-8")
    code, payload = _run(digest)
    assert code == 2
    assert payload.get("ok") is False


def test_machines_wrong_shape_exit2(tmp_path):
    digest = tmp_path / "dig"
    digest.mkdir()
    (digest / "digest.json").write_text(json.dumps({"machines": []}), encoding="utf-8")
    code, payload = _run(digest)
    assert code == 2
    assert payload.get("ok") is False


def test_wrapper_script_exists():
    assert WRAPPER.is_file()
