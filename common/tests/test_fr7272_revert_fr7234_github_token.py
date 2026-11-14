"""FR #7272: revert superseded #7253; no ear github.token Copilot provision; ASCII Common.ps1."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_PS1 = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL_BOB = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
START_BOB = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
FR7234_TEST = ROOT / "common" / "tests" / "test_fr7234_system_github_token.py"
FR7256_TEST = ROOT / "common" / "tests" / "test_fr7256_ensure_github_token_interactive.py"


def test_fr7272_bobiverse_common_bomless_ascii():
    raw = COMMON_PS1.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    bad = [i for i, b in enumerate(raw) if b > 127]
    assert bad == [], f"non-ASCII in Bobiverse-Common.ps1 at {bad[:10]}"


def test_fr7272_no_ear_github_token_provision_for_copilot():
    """FR #7272 / #7255: ears do not provision github.token for Copilot (Jeeves owns fleet)."""
    common = COMMON_PS1.read_text(encoding="utf-8")
    assert "function Ensure-BobiverseGithubToken" not in common
    assert "Ensure-BobiverseGithubToken" not in INSTALL_BOB.read_text(encoding="utf-8")
    assert "Ensure-BobiverseGithubToken" not in START_BOB.read_text(encoding="utf-8")
    assert not FR7234_TEST.is_file()
    assert not FR7256_TEST.is_file()
    # Keep FR #7006 interactive home helper for xAI; only Ensure is gone.
    assert "function Get-BobiverseInteractiveUserHome" in common
