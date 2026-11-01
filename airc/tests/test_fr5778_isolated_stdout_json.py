"""FR #5778: isolated worker stdout must stay pure JSON (identity-fallback logs break parse)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import airc_isolated as iso


def test_fr5778_extract_json_payload_ignores_leading_log_lines():
    blob = (
        "2026-11-01T16:29:30Z identity-fallback verb=network reason=credman-missing:x "
        "identity=system account=HOST$ target=PriorityAirc/NetworkAdmin\n"
        '{"ok":true,"action":"diag","hosts":[]}\n'
    )
    data = iso.extract_isolated_json_payload(blob)
    assert data == {"ok": True, "action": "diag", "hosts": []}


def test_fr5778_extract_json_payload_empty_is_none():
    assert iso.extract_isolated_json_payload("") is None
    assert iso.extract_isolated_json_payload("   \n") is None
    assert iso.extract_isolated_json_payload("not-json\nstill-not") is None


def test_fr5778_call_isolated_tolerates_log_prefix_on_stdout():
    payload = {"ok": True, "action": "diag", "hosts": []}
    noisy = (
        "2026-11-01T00:00:00Z identity-fallback verb=network reason=x "
        "identity=system account=HOST$ target=t\n"
        + json.dumps(payload, separators=(",", ":"))
        + "\n"
    )

    class P:
        returncode = 0
        stdout = noisy
        stderr = ""

    out = iso.call_isolated_module(
        "airc_network",
        "inventory_work",
        {"action": "diag", "whatif": True},
        runner=lambda *_a, **_k: P(),
    )
    assert out.get("ok") is True
    assert out.get("action") == "diag"
    assert out.get("error") != "worker_died"


def test_fr5778_child_env_marks_isolated_job():
    env = iso._child_env()
    assert env.get("AIRC_ISOLATED_JOB") == "1"


def test_fr5778_info_under_isolated_writes_stderr_not_stdout(monkeypatch, capsys):
    monkeypatch.setenv("AIRC_ISOLATED_JOB", "1")
    import airc_console_service as svc

    svc.info("identity-fallback verb=network reason=credman-missing:x")
    captured = capsys.readouterr()
    assert "identity-fallback" in captured.err
    assert "identity-fallback" not in captured.out


def test_fr5778_live_inventory_whatif_stdout_is_pure_json():
    """Source child: NETWORK whatif must not prepend logs on stdout."""
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts" / "airc_isolated.py"
    spec = json.dumps(
        {
            "module": "airc_network",
            "func": "inventory_work",
            "kwargs": {"action": "diag", "whatif": True},
        },
        separators=(",", ":"),
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "scripts") + os.pathsep + env.get("PYTHONPATH", "")
    # common/scripts for crash_report etc.
    common = root.parent / "common" / "scripts"
    if common.is_dir():
        env["PYTHONPATH"] = str(common) + os.pathsep + env["PYTHONPATH"]
    p = subprocess.run(
        [sys.executable, str(helper)],
        input=spec,
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    assert p.returncode == 0, p.stderr
    # Whole stdout must parse as one JSON object (no leading log line).
    data = json.loads((p.stdout or "").strip())
    assert isinstance(data, dict)
    assert "ok" in data
    # Fallback log may appear on stderr only.
    if "identity-fallback" in (p.stderr or ""):
        assert "identity-fallback" not in (p.stdout or "")
