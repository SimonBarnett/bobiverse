"""FR #4608: packaging pin - frozen jeeves must embed FR #2604/#4606 MRB exact-seat gitclaim."""

from __future__ import annotations

import importlib.util
import marshal
from pathlib import Path

import pytest

import assert_jeeves_gitclaim_embed as embed
import gitclaim

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "jeeves" / "scripts" / "Build-Jeeves.ps1"
ASSERT_PY = ROOT / "common" / "scripts" / "assert_jeeves_gitclaim_embed.py"
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"

STALE_SNIPPET = '''
def review_blocked_for_author(row, nick, live, ledger=None, *, free=None):
    """FR #2604 / #4606 doc kept but rule missing."""
    task = _canon_task(row)
    if task not in ("MRB", "UAT"):
        return False
    for author in row_author_seats(row):
        if nick_inherits_dead_seat(nick, author, live):
            return True
    return False
'''


def _src_code(text: str):
    return compile(text, "gitclaim.py", "exec")


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
    assert Path(gitclaim.__file__).resolve().name.startswith("gitclaim")


def test_fr4608_bytecode_check_accepts_tip_gitclaim():
    co = _src_code(GITCLAIM.read_text(encoding="utf-8"))
    assert embed.problems_in_module_code(co) == []


def test_fr4608_bytecode_check_rejects_stale_gitclaim():
    probs = embed.problems_in_module_code(_src_code(STALE_SNIPPET))
    assert any('"MRB" compare' in p for p in probs)


def test_fr4608_bytecode_check_rejects_mrb_after_inherit():
    src = STALE_SNIPPET.replace(
        "            return True\n    return False",
        "            return True\n        if task == \"MRB\":\n            continue\n    return False",
    )
    probs = embed.problems_in_module_code(_src_code(src))
    assert any("after nick_inherits_dead_seat" in p for p in probs)


def test_fr4608_pyc_file_roundtrip(tmp_path):
    co = _src_code(GITCLAIM.read_text(encoding="utf-8"))
    pyc = tmp_path / "gitclaim.cpython.pyc"
    pyc.write_bytes(b"\0" * 16 + marshal.dumps(co))
    embed.check_pyc_file(pyc)
    bad = tmp_path / "gitclaim.stale.pyc"
    bad.write_bytes(b"\0" * 16 + marshal.dumps(_src_code(STALE_SNIPPET)))
    with pytest.raises(SystemExit) as exc:
        embed.check_pyc_file(bad)
    assert "FR #4608" in str(exc.value)


def test_fr4608_real_pyz_not_zip(tmp_path):
    """Regression: PYZ is PyInstaller's format, not zip; read it via ZlibArchiveReader."""
    if importlib.util.find_spec("PyInstaller") is None:
        pytest.skip("PyInstaller not installed")
    from PyInstaller.archive.writers import ZlibArchiveWriter

    good = tmp_path / "good"
    good.mkdir()
    (good / "gitclaim.py").write_text(GITCLAIM.read_text(encoding="utf-8"), encoding="utf-8")
    pyz = good / "PYZ-00.pyz"
    ZlibArchiveWriter(
        str(pyz),
        [("gitclaim", str(good / "gitclaim.py"), "PYMODULE")],
        code_dict={"gitclaim": _src_code(GITCLAIM.read_text(encoding="utf-8"))},
    )
    assert embed.main([str(good)]) == 0

    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "gitclaim.py").write_text(STALE_SNIPPET, encoding="utf-8")
    ZlibArchiveWriter(
        str(stale / "PYZ-00.pyz"),
        [("gitclaim", str(stale / "gitclaim.py"), "PYMODULE")],
        code_dict={"gitclaim": _src_code(STALE_SNIPPET)},
    )
    with pytest.raises(SystemExit) as exc:
        embed.main([str(stale)])
    assert "stale" in str(exc.value)


def test_fr4608_main_allow_missing(tmp_path):
    assert embed.main([str(tmp_path / "missing"), "--allow-missing"]) == 2
