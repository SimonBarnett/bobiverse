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


def test_fr5778_call_isolated_preserves_bad_payload_classification():
    class P:
        returncode = 0
        stdout = "[]"
        stderr = ""

    out = iso.call_isolated_module(
        "airc_network",
        "inventory_work",
        runner=lambda *_a, **_k: P(),
    )
    assert out.get("error") == "worker_died"
    assert out.get("detail") == "bad-payload"


def test_fr5778_isolated_child_keeps_stdout_json_only(tmp_path):
    """Real child entry with deterministic stub --- no CredMan / directory network."""
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts" / "airc_isolated.py"
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    stub = (
        "import sys, types\n"
        "network = types.ModuleType('airc_network')\n"
        "def inventory_work(**kwargs):\n"
        "    from airc_console_service import info\n"
        "    info('identity-fallback test=isolated-child')\n"
        "    return {'ok': True, 'action': kwargs.get('action'), 'hosts': []}\n"
        "network.inventory_work = inventory_work\n"
        "sys.modules['airc_network'] = network\n"
    )
    (stub_dir / "sitecustomize.py").write_text(stub, encoding="utf-8")
    common = root.parent / "common" / "scripts"
    pythonpath = [str(stub_dir), str(root / "scripts")]
    if common.is_dir():
        pythonpath.append(str(common))
    if os.environ.get("PYTHONPATH"):
        pythonpath.append(os.environ["PYTHONPATH"])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    env.pop("AIRC_ISOLATED_JOB", None)
    spec = json.dumps(
        {
            "module": "airc_network",
            "func": "inventory_work",
            "kwargs": {"action": "diag"},
        },
        separators=(",", ":"),
    )
    p = subprocess.run(
        [sys.executable, str(helper)],
        input=spec,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {"ok": True, "action": "diag", "hosts": []}
    assert "identity-fallback test=isolated-child" in (p.stderr or "")

