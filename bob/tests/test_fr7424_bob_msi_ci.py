"""FR #7424: dedicated CI workflow builds only the bob MSI (no omnibus, no release)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-msi.yml"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
FETCH_WIX = ROOT / "common" / "scripts" / "Fetch-Wix.ps1"
# Flat scripts copy may also exist under scripts\
FETCH_WIX_FLAT = ROOT / "scripts" / "Fetch-Wix.ps1"


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr7424_bob_msi_workflow_exists_and_pins():
    assert WF.is_file(), "missing .github/workflows/build-bob-msi.yml"
    text = _wf()
    assert "name: build-bob-msi" in text
    assert "runs-on: windows-latest" in text
    assert "workflow_dispatch" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-msi" in text
    assert "MANIFEST.json" in text
    assert "Pack-BobiverseRelease.ps1" in text
    assert "-Product bob" in text or "Product bob" in text
    assert "Fetch-Wix.ps1" in text or "Fetch-Wix" in text
    # Only bob MSI — not sibling products in the same job.
    assert "-Product all" not in text
    assert "-Product jeeves" not in text
    assert "-Product airc" not in text
    # No GitHub release publish.
    for needle in (
        "gh release create",
        "softprops/action-gh-release",
        "actions/create-release",
        "ncipollo/release-action",
    ):
        assert needle not in text, f"must not publish release ({needle})"
    # Manifest fields required by FR.
    for field in ("source_commit", "msi_version", "msi_sha256", "embedded"):
        assert field in text
    assert "Get-FileHash -Algorithm SHA256" in text or "Get-FileHash" in text
    assert "setup-python@v5" in text
    assert "python-version: \"3.12\"" in text or "python-version: '3.12'" in text
    # Fail-closed: must not invoke -EmbedErgoPassword (comment may mention the switch).
    assert "-EmbedErgoPassword" not in text.replace("Do NOT pass -EmbedErgoPassword", "")
    assert "test_fr7424_bob_msi_ci.py" in text
    assert PACK.is_file()
    assert FETCH_WIX.is_file() or FETCH_WIX_FLAT.is_file()


def test_fr7424_pack_still_supports_product_bob_and_all():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "ValidateSet('all', 'jeeves', 'bob', 'airc')" in text or (
        "'bob'" in text and "'all'" in text
    )
    assert "[string]$Product = 'all'" in text or "$Product = 'all'" in text


def test_fr7424_workflow_version_is_three_part_upgrade_safe():
    text = _wf()
    # CI must compute a three-part MSI version that rises per run (FR #4389).
    assert "GITHUB_RUN_NUMBER" in text or "github.run_number" in text
    assert "ConvertTo-BobiverseMsiProductVersion" in text or "msi_version" in text
    assert "65535" in text  # MSI build field cap awareness
    # Pack downgrade gate needs gh auth in Actions (FR #6423 / #6949).
    assert "GH_TOKEN" in text
    assert "github.token" in text
    # Version must be derived at/above latest published (not raw VERSION patch alone).
    assert "Get-BobiverseLatestPublishedVersion" in text
