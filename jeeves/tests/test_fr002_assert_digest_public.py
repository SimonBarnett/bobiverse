"""FR #6142: Assert-BobDigestWebhookLocal ExpectedReportUrl + CheckPublic pins."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSERT = ROOT / "scripts" / "Assert-BobDigestWebhookLocal.ps1"
CANON = "https://bob.ntsa.uk/bob/v1/report"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr002_assert_has_expected_url_and_check_public():
    s = _txt(ASSERT)
    assert "FR #6142" in s
    assert "ExpectedReportUrl" in s
    assert CANON in s
    assert "CheckPublic" in s
    assert "Get-BobDigestReportUrl" in s
    assert "Get-BobDigestUrl" in s
    # Opt-in GET only; no POST / RestMethod in the public probe path.
    pub = s[s.index("if ($CheckPublic)") : s.index("if ($urlFail.Count")]
    assert "Invoke-WebRequest" in pub
    assert "-Method Get" in pub or "-Method GET" in pub
    assert "TimeoutSec 20" in pub
    assert "Invoke-RestMethod" not in pub
    assert "-Method Post" not in pub and "-Method POST" not in pub
    # Never dump digest body in evidence lines.
    assert "RawContent" not in pub
    assert ".Content" not in pub
