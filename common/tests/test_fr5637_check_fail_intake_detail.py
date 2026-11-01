"""FR #5637: no-matching-asset and asset-url-rejected Check intake must carry Detail.

After FR #5634, release-lookup-failed forwards kind= via Write-CheckFailIntake -Detail.
The other Invoke-Check Write-CheckFailIntake sites still omitted -Detail (MRB #5636 finding 3).
"""
from __future__ import annotations

from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def test_fr5637_no_matching_asset_passes_detail():
    t = UPD.read_text(encoding="utf-8")
    assert not UPD.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Write-CheckFailIntake -Result 'no-matching-asset'" in t
    # Must keep -Tag (FR #5354) and add -Detail with asset/tag context.
    idx = t.index("Write-CheckFailIntake -Result 'no-matching-asset'")
    call = t[idx : idx + 280]
    assert "-Tag" in call
    assert "-Detail" in call
    block_start = t.index("if (-not $msi -or -not $tagVer)")
    block = t[block_start : block_start + 550]
    assert "FR #5637" in block
    assert "assets=" in block or "$assetNames" in block


def test_fr5637_asset_url_rejected_passes_detail():
    t = UPD.read_text(encoding="utf-8")
    assert "Write-CheckFailIntake -Result 'asset-url-rejected'" in t
    idx = t.index("Write-CheckFailIntake -Result 'asset-url-rejected'")
    call = t[idx : idx + 280]
    assert "-Tag" in call
    assert "-Detail" in call
    needle = "if (-not (Test-AssetUrl -Url $msiUrl) -or -not (Test-AssetUrl -Url $shaUrl))"
    block_start = t.index(needle)
    block = t[block_start : block_start + 500]
    assert "FR #5637" in block
    assert "msiUrl" in block or "shaUrl" in block


def test_fr5637_docs_name_check_fail_detail():
    skill = SKILL.read_text(encoding="utf-8")
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "5637" in skill
    assert "no-matching-asset" in skill or "asset-url-rejected" in skill
    assert "detail=" in skill.lower() or "-Detail" in skill
