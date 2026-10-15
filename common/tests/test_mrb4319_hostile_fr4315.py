"""MRB #4319 hostile pin: FR #4315 digest-home isolation needles stay on main."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOB_HOME = ROOT / "scripts" / "bob_home.py"
BUILD = ROOT / "scripts" / "bobiverse_build.py"
CONFTEST = ROOT / "tests" / "conftest.py"
PS1 = ROOT / "scripts" / "Bobiverse-Common.ps1"


def test_mrb4319_admin_profile_redirects_under_build_suite():
    text = BOB_HOME.read_text(encoding="utf-8-sig")
    assert "FR #4315" in text
    assert "BOBIVERSE_BUILD_SUITE" in text
    assert "def _admin_profile" in text
    # Under build suite must return redirected profile, not hard-coded Administrator.
    assert "_env_truthy(\"BOBIVERSE_BUILD_SUITE\")" in text or "_env_truthy('BOBIVERSE_BUILD_SUITE')" in text


def test_mrb4319_guarded_run_isolation_wins_over_suite_env():
    text = BUILD.read_text(encoding="utf-8-sig")
    assert "Isolation last so suite.env cannot point BOB_DIGEST_HOME" in text or "Isolation home/URL keys always win" in text
    assert "merged.update(iso)" in text


def test_mrb4319_conftest_pins_digest_home_when_unset():
    text = CONFTEST.read_text(encoding="utf-8-sig")
    assert "FR #4315" in text
    assert "BOB_DIGEST_HOME" in text
    assert "_fr4315_isolate_digest_home" in text


def test_mrb4319_ps1_skips_admin_bobiverse_under_build_suite():
    text = PS1.read_text(encoding="utf-8-sig")
    assert "FR #4315" in text
    assert "BOBIVERSE_BUILD_SUITE" in text
    assert "Users\\Administrator\\.bobiverse" in text or "Users\Administrator\.bobiverse" in text
