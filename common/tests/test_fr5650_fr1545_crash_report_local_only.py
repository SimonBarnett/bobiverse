"""FR #5650: test_fr1545 Apply VerifyOnly must set BOB_CRASH_REPORT=local-only.

FR #5642 covered shared env fixtures; fr1545 still used raw subprocess.run
without env, so Apply VerifyOnly could POST live FR #5279 intake.
"""
from __future__ import annotations

from repo_layout import ROOT

FR1545 = ROOT / "common/tests/test_fr1545_updater_download_timeout.py"


def test_fr5650_fr1545_apply_sets_crash_report_local_only():
    t = FR1545.read_text(encoding="utf-8")
    assert not FR1545.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "FR #5650" in t or "FR #5642" in t
    idx = t.index("def test_fr1545_apply_local_asset_still_works")
    chunk = t[idx : idx + 2200]
    assert 'e["BOB_CRASH_REPORT"] = "local-only"' in chunk
    assert 'e["BOBIVERSE_CRASH_REPORT"] = "local-only"' in chunk
    assert "env=e" in chunk
    # Must not leave a bare Apply subprocess.run without env= in that test.
    assert "subprocess.run(args, capture_output=True, text=True, env=e" in chunk
