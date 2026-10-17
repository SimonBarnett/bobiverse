"""FR #3975: CI must run BOM-less ASCII gates on every PR (not only gitclaim)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "pytest-ascii-bom.yml"

# Files that went red on v0.1.31 (#3966) when comment-only Unicode slipped in.
WATCHED = (
    ROOT / "airc" / "scripts" / "Install-Airc.ps1",
    ROOT / "airc" / "scripts" / "Install-AircConsole.ps1",
    ROOT / "bob" / "scripts" / "Ensure-BobTrayRunning.ps1",
    ROOT / "common" / "scripts" / "intake.py",
)

REQUIRED_SUITE = (
    "airc/tests/test_fr2499_install_airc_console_parse.py",
    "airc/tests/test_fr3391_install_airc_parse.py",
    "airc/tests/test_mrb2501_hostile_install_airc_parse.py",
    "airc/tests/test_fr3756_install_ergo_pass_fallback.py",
    "airc/tests/test_fr4380_install_ascii_emdash.py",
    "jeeves/tests/test_mrb3757_hostile_fr3756.py",
    "jeeves/tests/test_mrb3760_hostile_fr3759.py",
    "common/tests/test_fr611_intake_error_body.py",
    "common/tests/test_mrb2936_hostile_stale_pin_green.py",
    "common/tests/test_mrb3569_hostile_fr3563_stale_pins.py",
    "jeeves/tests/test_fr3975_ci_ascii_bom_gates.py",
)


def test_fr3975_ascii_bom_workflow_exists():
    assert WF.is_file(), f"missing CI workflow: {WF}"


def test_fr3975_workflow_runs_on_every_pr_and_gates_suite():
    text = WF.read_text(encoding="utf-8")
    assert "pull_request" in text
    assert "windows-latest" in text
    assert "pytest" in text.lower()
    # Cheap every-PR job: do not path-filter away Install-*.ps1 / intake.py only changes
    # (path filters are allowed as additive, but pull_request without exclusive
    # narrow paths must still fire for the watched scripts).
    for needle in REQUIRED_SUITE:
        assert needle.replace("\\", "/") in text.replace("\\", "/"), f"missing suite entry: {needle}"
    for path in (
        "airc/scripts/Install-Airc.ps1",
        "airc/scripts/Install-AircConsole.ps1",
        "bob/scripts/Ensure-BobTrayRunning.ps1",
        "common/scripts/intake.py",
    ):
        assert path in text, f"workflow must name watched file {path}"


def test_fr3975_watched_scripts_are_bomless_ascii():
    """Local pin so the CI suite is meaningful even before Actions runs."""
    for path in WATCHED:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM on {path}"
        assert all(b < 128 for b in raw), f"non-ASCII in {path}"
