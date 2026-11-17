"""FR #7987: isolated installer_legion_work died with worker_died/bad-json.

The parent remapped a real child result to ``worker_died`` / ``bad-json`` when
stdout carried log text on the same line as the JSON object (older build or a
dependency printing to stdout). Keep the IPC channel JSON-only in the child and
accept a JSON object anywhere on a line in the parent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import airc_isolated as iso


def test_fr7987_extract_json_after_same_line_log_prefix():
    blob = '2026-11-17T04:57:17Z info thing=1 {"ok":true,"hosts":[]}'
    assert iso.extract_isolated_json_payload(blob) == {"ok": True, "hosts": []}


def test_fr7987_extract_json_with_trailing_log_suffix():
    blob = '{"ok":true,"detail":"x"} note=trailing\r\n'
    assert iso.extract_isolated_json_payload(blob) == {"ok": True, "detail": "x"}


def test_fr7987_extract_tolerates_bom_and_utf16_nul_bytes():
    blob = "\ufeff" + "{\x00\"\x00o\x00k\x00\"\x00:\x00t\x00r\x00u\x00e\x00}\x00"
    assert iso.extract_isolated_json_payload(blob) == {"ok": True}


def test_fr7987_extract_pretty_printed_object():
    blob = 'log before\n{\n  "ok": true,\n  "target": "localhost"\n}\nlog after'
    assert iso.extract_isolated_json_payload(blob) == {"ok": True, "target": "localhost"}


def test_fr7987_extract_still_none_for_non_json():
    assert iso.extract_isolated_json_payload("still-not-json") is None


def test_fr7987_call_isolated_does_not_remap_prefixed_result():
    class P:
        returncode = 0
        stdout = 'no-newline-prefix {"ok":true,"action":"legion"}'
        stderr = ""

    out = iso.call_isolated_module(
        "airc_legion",
        "installer_legion_work",
        {"target": "localhost", "whatif": True},
        runner=lambda *_a, **_k: P(),
    )
    assert out == {"ok": True, "action": "legion"}


def test_fr7987_child_stray_stdout_print_goes_to_stderr(tmp_path):
    """A dependency printing to stdout mid-work must not corrupt the IPC JSON."""
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts" / "airc_isolated.py"
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    stub = (
        "import sys, types\n"
        "legion = types.ModuleType('airc_legion')\n"
        "def installer_legion_work(**kwargs):\n"
        "    print('NOISE-ON-BARE-STDOUT')\n"
        "    return {'ok': True, 'target': kwargs.get('target')}\n"
        "legion.installer_legion_work = installer_legion_work\n"
        "sys.modules['airc_legion'] = legion\n"
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
            "module": "airc_legion",
            "func": "installer_legion_work",
            "kwargs": {"target": "localhost", "whatif": True},
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
    assert json.loads(p.stdout) == {"ok": True, "target": "localhost"}
    assert "NOISE-ON-BARE-STDOUT" not in (p.stdout or "")
    assert "NOISE-ON-BARE-STDOUT" in (p.stderr or "")
