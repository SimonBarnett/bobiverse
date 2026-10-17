"""FR #4608: packaging pin — frozen jeeves must embed FR #2604/#4606 MRB exact-seat gitclaim."""

from __future__ import annotations

import zipfile
from pathlib import Path

import assert_jeeves_gitclaim_embed as embed
import gitclaim

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "jeeves" / "scripts" / "Build-Jeeves.ps1"
ASSERT_PY = ROOT / "common" / "scripts" / "assert_jeeves_gitclaim_embed.py"
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"


def test_fr4608_build_jeeves_hidden_imports_gitclaim():
    text = BUILD.read_text(encoding="utf-8")
    assert "'gitclaim'" in text or '"gitclaim"' in text
    assert "FR #4608" in text
    assert "assert_jeeves_gitclaim_embed" in text


def test_fr4608_assert_script_and_source_markers():
    assert ASSERT_PY.is_file()
    src = GITCLAIM.read_text(encoding="utf-8")
    assert "FR #2604 / #4606" in src
    assert 'if task == "MRB":' in src
    assert "nick_inherits_dead_seat" in src
    # Source module import path matches what PyInstaller freezes.
    loaded = Path(gitclaim.__file__).resolve()
    assert loaded.name.startswith("gitclaim")


def test_fr4608_pyz_checker_accepts_fixture_with_markers(tmp_path):
    pyz = tmp_path / "PYZ-00.pyz"
    good = (
        b'x' * 16
        + b"FR #2604 / #4606"
        + b'if task == "MRB":'
        + b"nick_inherits_dead_seat"
        + b"y" * 8
    )
    with zipfile.ZipFile(pyz, "w") as zf:
        zf.writestr("gitclaim.pyc", good)
    embed.check_pyz(pyz)


def test_fr4608_pyz_checker_rejects_stale_gitclaim(tmp_path):
    pyz = tmp_path / "PYZ-00.pyz"
    stale = b"nick_inherits_dead_seat only, no MRB continue" + b"FR #2604"
    with zipfile.ZipFile(pyz, "w") as zf:
        zf.writestr("gitclaim.pyc", stale)
    try:
        embed.check_pyz(pyz)
        raise AssertionError("expected SystemExit for stale embed")
    except SystemExit as exc:
        assert "FR #4608" in str(exc)


def test_fr4608_main_allow_missing(tmp_path):
    code = embed.main([str(tmp_path / "missing"), "--allow-missing"])
    assert code == 2
