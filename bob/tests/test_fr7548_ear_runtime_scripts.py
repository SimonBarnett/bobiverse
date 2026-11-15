"""FR #7548: ear artifact ships disk scripts and startup rejects a mismatch."""
from __future__ import annotations

import hashlib
from pathlib import Path

import irc_agent
from repo_layout import REPO

WF = REPO / ".github" / "workflows" / "build-bob-ear.yml"
INSTALL = REPO / "bob" / "scripts" / "Install-BobEarExe.ps1"


def test_fr7548_workflow_ships_runtime_scripts_with_hashes():
    text = WF.read_text(encoding="utf-8")
    for name in irc_agent.EAR_RUNTIME_DISK_SCRIPTS:
        assert name in text
        assert f"common\\scripts\\{name}" in text or f"common/scripts/{name}" in text
        key = irc_agent.runtime_script_provenance_key(name)
        assert key in text
    inst = INSTALL.read_text(encoding="utf-8-sig")
    for name in irc_agent.EAR_RUNTIME_DISK_SCRIPTS:
        assert name in inst


def test_fr7548_hash_mismatch_and_missing_are_refused(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    body = b"print('ear-script')\n"
    (scripts / "bobreport.py").write_bytes(body)
    (scripts / "opencode_fuel.py").write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    prov = scripts / "provenance.txt"
    lines = [
        f"{irc_agent.runtime_script_provenance_key(n)}={digest}"
        for n in irc_agent.EAR_RUNTIME_DISK_SCRIPTS
    ]
    prov.write_text("\n".join(lines) + "\n", encoding="utf-8")
    irc_agent.assert_ear_runtime_scripts(scripts, prov)
    (scripts / "bobreport.py").write_bytes(b"print('stale')\n")
    try:
        irc_agent.assert_ear_runtime_scripts(scripts, prov)
        raise AssertionError("mismatch must refuse")
    except RuntimeError as exc:
        assert "hash mismatch" in str(exc)
    (scripts / "opencode_fuel.py").unlink()
    (scripts / "bobreport.py").write_bytes(body)
    try:
        irc_agent.assert_ear_runtime_scripts(scripts, prov)
        raise AssertionError("missing must refuse")
    except RuntimeError as exc:
        assert "missing" in str(exc)


def test_fr7548_enforce_reports_and_exits(tmp_path: Path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    seen: list[str] = []

    def _report(exe, exc_type, exc_value, tb, **kwargs):
        seen.append(str(exe))
        assert "password" not in str(exc_value)
        return {"ok": True}

    import crash_report

    monkeypatch.setattr(crash_report, "report_exception", _report)
    try:
        irc_agent.enforce_ear_runtime_scripts(scripts, scripts / "provenance.txt")
        raise AssertionError("must exit")
    except SystemExit as exc:
        assert exc.code == 2
    assert seen == ["bob-ear"]
