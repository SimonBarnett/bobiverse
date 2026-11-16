# -*- coding: utf-8 -*-
"""FR #7884: $wedgePy is an installed script, not a PyInstaller _MEI extract."""
from __future__ import annotations

import re
from pathlib import Path

import bob_worker as bw

OP = r"C:\Tools\opencode.exe"


def _script(spec) -> str:
    return next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))


def test_fr7884_wedge_path_is_installed_not_mei(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    wedge = scripts / "opencode_tool_wedge.py"
    wedge.write_text("# wedge\n", encoding="utf-8")
    guard = scripts / "opencode_turn_guard.py"
    guard.write_text("# guard\n", encoding="utf-8")
    mei = tmp_path / "_MEI000012702" / "opencode_tool_wedge.py"
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "seat"),
        "Do work.",
        OP,
        tmp_path / "run",
        install_root=tmp_path,
    )
    script = _script(spec)
    assert f"$wedgePy = '{wedge}'" in script
    assert "_MEI" not in script.split("$wedgePy =", 1)[1].split("\n", 1)[0]
    assert str(mei) not in script
    handed = re.findall(r"\$\w+Py = '([^']+\.py)'", script)
    assert handed
    for path in handed:
        assert "_MEI" not in path
        assert Path(path).is_file()


def test_fr7884_missing_wedge_still_builds_and_reports(tmp_path: Path, monkeypatch):
    reports = []

    def fake(component, message, site=""):
        reports.append((component, site, message))
        return {"ok": True}

    monkeypatch.setattr(bw, "_report_missing_worker_script", lambda name: fake("bob-worker", name, "opencode-helper-missing"))
    monkeypatch.setattr(bw, "_resolve_installed_worker_script", lambda name, **_k: None if name == "opencode_tool_wedge.py" else Path("x"))
    # Guard falls back when resolver returns None only for the wedge name.
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "seat"),
        "Do work.",
        OP,
        tmp_path / "run",
        install_root=tmp_path / "empty",
    )
    script = _script(spec)
    assert "$wedgePy = ''" in script
    assert "try { $wedgeLine" in script
    assert reports and reports[0][2] == "opencode_tool_wedge.py"
