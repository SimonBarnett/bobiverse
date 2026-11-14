"""FR #6254 / #7179: ear CI provenance + deploy-pool-monitor manifest.

FR #7179 dropped the hard behavior pin from build-bob-ear.yml so main/PR builds
compile the checked-out tip. Provenance records source_commit=workflow commit.
deploy-pool-monitor-manifest.txt remains a deploy note list (hashes may lag tip);
it is copied into the artifact and is not a CI gate.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"
MANIFEST = ROOT / "bob" / "docs" / "deploy-pool-monitor-manifest.txt"

BEHAVIOR_FILES = [
    "common/scripts/bobreport.py",
    "common/scripts/irc_agent.py",
    "common/scripts/opencode_fuel.py",
    "common/scripts/bobiverse_build.py",
    "bob/tray/src/Public/Get-BobTrayHover.ps1",
    "bob/tray/src/Private/Get-BobIrc.ps1",
    "bob/tray/tools/Watch-BobTray.ps1",
    "bob/tray/tools/Get-BobOpencodeFuel.ps1",
    "bob/tray/src/BobBridge.psm1",
]

# Historical pins --- must not reappear as a live $expected gate in the workflow.
STALE_PIN = "99783eb90c23a9ee8bb9bbd326a6de0500de1d8f"
STALE_D563 = "d563eca67adf1f73213628d8eb4b2dc2f308b73c"
FR6558_MERGE = "2da1eb06d0c99cd3384d6bf1bb21faa830526ba5"
FR7065_PIN = "4a7f54f6564c22d013d2b0fa577438f11034a537"


def _workflow_text() -> str:
    return WF.read_text(encoding="utf-8")


def _crlf_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def test_workflow_builds_tip_without_hard_pin():
    text = _workflow_text()
    assert "Confirm behavior files match" not in text
    assert re.search(r'\$expected\s*=\s*"[0-9a-f]{40}"', text) is None
    assert f"behavior_source_sha={FR7065_PIN}" not in text
    assert "source_commit=$($env:WORKFLOW_COMMIT)" in text
    assert "workflow_commit=$($env:WORKFLOW_COMMIT)" in text
    assert "persist-credentials: false" in text
    assert "bobiverse_build.py" in text
    assert "push:" in text
    assert "branches: [main]" in text
    # History comment may still cite FR #6558 merge; that is not a live gate.
    assert FR6558_MERGE in text or "6558" in text or "Prior pin" in text or "deploy-pool-monitor" in text


def test_provenance_template_binds_checkout_commit():
    text = _workflow_text()
    assert "exe_sha256=$hash" in text or "exe_sha256=" in text
    assert "bob-ear.exe.sha256" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-ear" in text
    # No hardcoded 40-hex behavior_source_sha= line in the provenance template.
    assert re.search(r"behavior_source_sha=[0-9a-f]{40}", text) is None


def test_manifest_lists_behavior_paths():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "Behavior source sha:" in text or "Source-pass parent:" in text
    assert "bob-ear" in text
    assert "bobiverse_build" in text
    assert "CRLF" in text or "crlf" in text
    for rel in BEHAVIOR_FILES:
        assert rel in text or rel.replace("/", "\\") in text, f"manifest missing {rel}"
    # FR #7179: manifest notes that CI no longer gates on the pin.
    assert "7179" in text or "not a CI gate" in text.lower() or "deploy note" in text.lower()
    assert "workflow guard" not in text.lower()


def test_manifest_sha_rows_are_well_formed():
    """Rows stay parseable; tip drift is allowed (deploy note, not CI pin)."""
    text = MANIFEST.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+(\d+)\s+(\S.+)$", line.strip())
        if m:
            rows.append((m.group(1), int(m.group(2)), m.group(3).replace("\\", "/")))
    assert rows, "manifest missing sha256 rows"
    by_path = {path: (digest, size) for digest, size, path in rows}
    for rel in BEHAVIOR_FILES:
        assert rel in by_path, f"manifest missing row for {rel}"
    # Each digest must be 64 hex; size positive. Tip match is not required.
    for rel, (digest, size) in by_path.items():
        assert re.fullmatch(r"[0-9a-f]{64}", digest), rel
        assert size > 0, rel
        assert (ROOT / rel).is_file(), rel


def test_stale_workflow_pin_literals_are_not_live_gates():
    text = _workflow_text()
    assert STALE_PIN not in text
    assert STALE_D563 not in text
    # FR7065 pin may appear only in comments / history pointing at the manifest.
    if FR7065_PIN in text:
        assert "Confirm behavior files match" not in text
        assert f'expected = "{FR7065_PIN}"' not in text
        assert f"$expected = \"{FR7065_PIN}\"" not in text
