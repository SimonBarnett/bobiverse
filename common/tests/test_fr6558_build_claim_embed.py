"""FR #6558 / #6576: packaging pin - frozen ear/jeeves must embed build-route claim code."""

from __future__ import annotations

import importlib.util
import marshal
from pathlib import Path

import pytest

import assert_build_claim_embed as embed

ROOT = Path(__file__).resolve().parents[2]
BUILD_EAR = ROOT / "bob" / "scripts" / "Build-BobEar.ps1"
BUILD_JEEVES = ROOT / "jeeves" / "scripts" / "Build-Jeeves.ps1"
ASSERT_PY = ROOT / "common" / "scripts" / "assert_build_claim_embed.py"
SRC = ROOT / "common" / "scripts" / "bobiverse_build.py"
DETAIL = "_claim_build_route_marker_detail"

STALE_SNIPPET = '''
def claim_build_route_marker(marker_dir, route_id):
    """Old permanent claim only."""
    return True

def consume_build_v1(line, local_machine, recipe_machine, *, queue_dir=None, route_marker_dir=None):
    return True
'''


def _src_code(text: str):
    return compile(text, "bobiverse_build.py", "exec")


def test_fr6558_builders_call_assert_fail_closed():
    ear = BUILD_EAR.read_text(encoding="utf-8")
    jeeves = BUILD_JEEVES.read_text(encoding="utf-8")
    for text, label in ((ear, "Build-BobEar"), (jeeves, "Build-Jeeves")):
        assert "assert_build_claim_embed" in text, label
        assert "FR #6558" in text or "FR #6576" in text, label
        # Fail closed: missing helper must throw (no warn-and-skip for this pin).
        assert "assert_build_claim_embed.py missing; skip" not in text
        assert "throw" in text.lower() or "Throw" in text


def test_fr6558_assert_script_and_source_markers():
    assert ASSERT_PY.is_file()
    src = SRC.read_text(encoding="utf-8")
    assert DETAIL in src
    assert "stale_after_s" in src
    assert "stale_claim_s" in src
    assert ".reclaim.lock" in src
    assert "def consume_build_v1" in src


def test_fr6558_bytecode_check_accepts_tip_bobiverse_build():
    co = _src_code(SRC.read_text(encoding="utf-8"))
    assert embed.problems_in_module_code(co) == []


def test_fr6558_bytecode_check_rejects_stale_bobiverse_build():
    probs = embed.problems_in_module_code(_src_code(STALE_SNIPPET))
    assert probs
    assert any("stale_after_s" in p or DETAIL in p or "reclaim" in p for p in probs)


def test_fr6558_pyc_file_roundtrip(tmp_path):
    co = _src_code(SRC.read_text(encoding="utf-8"))
    pyc = tmp_path / "bobiverse_build.cpython.pyc"
    pyc.write_bytes(b"\0" * 16 + marshal.dumps(co))
    embed.check_pyc_file(pyc)
    bad = tmp_path / "bobiverse_build.stale.pyc"
    bad.write_bytes(b"\0" * 16 + marshal.dumps(_src_code(STALE_SNIPPET)))
    with pytest.raises(SystemExit) as exc:
        embed.check_pyc_file(bad)
    assert "FR #6558" in str(exc.value)


def test_fr6558_real_pyz_when_pyinstaller_present(tmp_path):
    if importlib.util.find_spec("PyInstaller") is None:
        pytest.skip("PyInstaller not installed")
    from PyInstaller.archive.writers import ZlibArchiveWriter

    good = tmp_path / "good"
    good.mkdir()
    tip = SRC.read_text(encoding="utf-8")
    (good / "bobiverse_build.py").write_text(tip, encoding="utf-8")
    pyz = good / "PYZ-00.pyz"
    ZlibArchiveWriter(
        str(pyz),
        [("bobiverse_build", str(good / "bobiverse_build.py"), "PYMODULE")],
        code_dict={"bobiverse_build": _src_code(tip)},
    )
    assert embed.main([str(good)]) == 0

    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "bobiverse_build.py").write_text(STALE_SNIPPET, encoding="utf-8")
    ZlibArchiveWriter(
        str(stale / "PYZ-00.pyz"),
        [("bobiverse_build", str(stale / "bobiverse_build.py"), "PYMODULE")],
        code_dict={"bobiverse_build": _src_code(STALE_SNIPPET)},
    )
    with pytest.raises(SystemExit) as exc:
        embed.main([str(stale)])
    assert "stale" in str(exc.value).lower() or "FR #6558" in str(exc.value)


def test_fr6558_main_allow_missing(tmp_path):
    assert embed.main([str(tmp_path / "missing"), "--allow-missing"]) == 2
