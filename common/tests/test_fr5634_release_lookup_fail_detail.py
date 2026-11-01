"""FR #5634: release-lookup-failed Check intake must carry kind= detail.

MarchHare filed product=airc result=release-lookup-failed with detail= empty
while the updater log already had kind=rate-limited|http-N|offline-or-error.
Write-CheckFailIntake omitted -Detail; triage could not tell transient API
errors from no-matching-release-after-latest-404.
"""
from __future__ import annotations

from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def test_fr5634_write_check_fail_intake_forwards_detail():
    t = UPD.read_text(encoding="utf-8")
    assert not UPD.read_bytes().startswith(b"\xef\xbb\xbf")
    fn = t[t.index("function Write-CheckFailIntake") : t.index("function Ensure-ServiceRunning")]
    assert "FR #5634" in fn
    assert "[string]$Detail" in fn
    assert "Send-BobiverseUpdateFailureIntake" in fn
    assert "-Detail $Detail" in fn


def test_fr5634_release_lookup_failed_passes_kind_detail():
    t = UPD.read_text(encoding="utf-8")
    assert "Write-CheckFailIntake -Result 'release-lookup-failed'" in t
    # Must pass kind= (and ideally exception message) into intake Detail.
    assert "Write-CheckFailIntake -Result 'release-lookup-failed' -Detail" in t
    block_start = t.index("try { $rel = Get-LatestRelease } catch {")
    block = t[block_start : block_start + 900]
    assert "kind=$kind" in block or 'kind={0}' in block or "kind={0}" in block
    assert "-Detail" in block
    assert "FR #5634" in block or "FR #5634" in t[t.index("function Write-CheckFailIntake") :]


def test_fr5634_docs_name_release_lookup_detail():
    skill = SKILL.read_text(encoding="utf-8")
    assert "release-lookup-failed" in skill
    assert "5634" in skill or "kind=" in skill
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
