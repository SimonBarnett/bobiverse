"""FR #6254: ear build pin + deploy manifest must match reviewed pool behavior on tip.

Packaging repair only: do not weaken the git-diff guard. A stale pin (e.g. 99783eb)
must fail alignment while the declared behavior_source_sha must pass.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"
MANIFEST = ROOT / "bob" / "docs" / "deploy-pool-monitor-manifest.txt"

BEHAVIOR_FILES = [
    "common/scripts/bobreport.py",
    "common/scripts/irc_agent.py",
    "common/scripts/opencode_fuel.py",
    "bob/tray/src/Public/Get-BobTrayHover.ps1",
    "bob/tray/src/Private/Get-BobIrc.ps1",
    "bob/tray/tools/Watch-BobTray.ps1",
    "bob/tray/tools/Get-BobOpencodeFuel.ps1",
    "bob/tray/src/BobBridge.psm1",
]

STALE_PIN = "99783eb90c23a9ee8bb9bbd326a6de0500de1d8f"


def _workflow_text() -> str:
    return WF.read_text(encoding="utf-8")


def _pin_from_workflow(text: str) -> str:
    m = re.search(r'\$expected\s*=\s*"([0-9a-f]{40})"', text)
    assert m, "workflow missing $expected behavior pin"
    return m.group(1)


def _provenance_behavior_sha(text: str) -> str:
    m = re.search(r"behavior_source_sha=([0-9a-f]{40})", text)
    assert m, "provenance template missing behavior_source_sha"
    return m.group(1)


def _git_diff_stat(sha: str) -> str:
    proc = subprocess.run(
        ["git", "diff", "--stat", sha, "--", *BEHAVIOR_FILES],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def test_workflow_pin_matches_provenance_template():
    text = _workflow_text()
    pin = _pin_from_workflow(text)
    assert _provenance_behavior_sha(text) == pin
    assert STALE_PIN not in text
    assert "Confirm behavior files match" in text
    assert "persist-credentials: false" in text


def test_declared_pin_aligns_with_tip_behavior_files():
    pin = _pin_from_workflow(_workflow_text())
    # Packaging commits may sit ahead of the pin; the eight behavior blobs must match.
    out = _git_diff_stat(pin)
    assert out.strip() == "", f"behavior files drifted from pin {pin}:\n{out}"


def test_stale_99783eb_pin_is_rejected_by_diff_guard():
    """Regression: the pre-#6252 pin must not appear aligned with current tip."""
    out = _git_diff_stat(STALE_PIN)
    assert out.strip(), "expected stale pin 99783eb to differ from tip behavior files"
    # At least the known drifted modules from the FR evidence.
    assert "bobreport.py" in out or "opencode_fuel.py" in out or "Get-BobIrc.ps1" in out


def test_manifest_hashes_match_tip_bytes():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "Source-pass parent:" in text or "Behavior source sha:" in text
    rows = []
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+(\d+)\s+(\S.+)$", line.strip())
        if m:
            rows.append((m.group(1), int(m.group(2)), m.group(3).replace("\\", "/")))
    assert rows, "manifest missing sha256 rows"
    by_path = {path.replace("\\", "/"): (digest, size) for digest, size, path in rows}
    for rel in BEHAVIOR_FILES:
        assert rel in by_path, f"manifest missing {rel}"
    # Every declared row (behavior + deploy scripts) must match tip bytes.
    for rel, (want_digest, want_size) in by_path.items():
        data = (ROOT / rel).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        size = len(data)
        assert (digest, size) == (want_digest, want_size), (
            f"manifest hash mismatch for {rel}: "
            f"manifest={(want_digest, want_size)} tip=({digest}, {size})"
        )


def test_manifest_names_behavior_source_sha():
    text = MANIFEST.read_text(encoding="utf-8")
    pin = _pin_from_workflow(_workflow_text())
    assert pin in text
    assert "bob-ear" in text
    # Tray Status dialogs are separate from the ear PyInstaller pin set.
    assert "OpencodePaint" in text or "BobStatus" in text or "Build-BobDialogs" in text
