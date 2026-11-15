"""FR #7426: dedicated CI workflow builds only the airc MSI (no omnibus, no release)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-airc-msi.yml"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
FETCH_WIX = ROOT / "common" / "scripts" / "Fetch-Wix.ps1"


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr7426_airc_msi_workflow_exists_and_pins():
    assert WF.is_file(), "missing .github/workflows/build-airc-msi.yml"
    text = _wf()
    assert "name: build-airc-msi" in text
    assert "runs-on: windows-latest" in text
    assert "workflow_dispatch" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "upload-artifact@v4" in text
    assert "name: airc-msi" in text
    assert "MANIFEST.json" in text
    assert "Pack-BobiverseRelease.ps1" in text
    assert "-Product airc" in text or "Product airc" in text
    assert "Fetch-Wix.ps1" in text or "Fetch-Wix" in text
    assert "-Product all" not in text
    assert "-Product bob" not in text
    assert "-Product jeeves" not in text
    for needle in (
        "gh release create",
        "softprops/action-gh-release",
        "actions/create-release",
        "ncipollo/release-action",
    ):
        assert needle not in text, f"must not publish release ({needle})"
    for field in ("source_commit", "msi_version", "msi_sha256", "embedded"):
        assert field in text
    assert "Get-FileHash" in text
    assert "setup-python@v5" in text
    assert "python-version: \"3.12\"" in text or "python-version: '3.12'" in text
    assert "test_fr7426_airc_msi_ci.py" in text
    assert "airc.exe" in text
    # FR #4216: secret via env, fail closed, never echo value into MANIFEST.
    assert "AIRC_PACK_ERGO_PASSWORD" in text
    assert "secrets.AIRC_PACK_ERGO_PASSWORD" in text
    assert "fail-closed" in text or "fail closed" in text.lower() or "missing or empty" in text
    assert "value not printed" in text.lower() or "never printed" in text.lower() or "not printed" in text
    assert "MANIFEST would contain Ergo PASS" in text or "refuse: MANIFEST" in text
    assert PACK.is_file()
    assert FETCH_WIX.is_file()


def test_fr7426_pack_still_supports_product_airc_and_all():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "ValidateSet('all', 'jeeves', 'bob', 'airc')" in text
    assert "$wantEmbedErgo = $EmbedErgoPassword -or ($Name -eq 'airc')" in text


def test_fr7426_workflow_version_is_three_part_upgrade_safe():
    text = _wf()
    assert "GITHUB_RUN_NUMBER" in text or "github.run_number" in text
    assert "ConvertTo-BobiverseMsiProductVersion" in text or "msi_version" in text
    assert "65535" in text
    # Pack downgrade gate needs gh auth in Actions (FR #6423 / #6949).
    assert "GH_TOKEN" in text
    assert "github.token" in text
    assert "Get-BobiverseLatestPublishedVersion" in text
