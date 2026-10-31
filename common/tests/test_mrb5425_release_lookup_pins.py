"""MRB #5425 hostile pins for FR #5353 /releases/latest 404 fallback."""
from __future__ import annotations

from repo_layout import ROOT


def test_mrb5425_updater_and_docs_name_list_fallback():
    src = (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8")
    doc = (ROOT / "common" / "docs" / "post-install.md").read_text(encoding="utf-8")
    assert "FR #5353" in src
    assert "latest-endpoint-404" in src
    assert "Select-BestReleaseFromList" in src
    assert "releases?per_page=" in src
    assert "FR #5353" in doc
    assert "/releases/latest" in doc
    assert "non-prerelease" in doc
    assert not (ROOT / "common" / "docs" / "post-install.md").read_bytes().startswith(b"\xef\xbb\xbf")
