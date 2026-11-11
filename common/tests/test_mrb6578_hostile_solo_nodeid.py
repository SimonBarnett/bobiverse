"""MRB #6578 hostile: FR #6561 solo pytest runs only the failing nodeid."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb

ROOT = Path(__file__).resolve().parents[2]
BUILD_PY = ROOT / "common" / "scripts" / "bobiverse_build.py"
DOCS = ROOT / "docs" / "bobiverse-build.md"


def test_mrb6578_source_has_keep_and_valued_opts():
    src = BUILD_PY.read_text(encoding="utf-8")
    assert "def _keep_pytest_option_tokens" in src
    assert "_PYTEST_OPTS_WITH_VALUE" in src
    assert "FR #6561" in src
    assert "drop positional" in src.lower() or "Drops positional" in src
    assert not BUILD_PY.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6578_docs_mention_solo_strip():
    docs = DOCS.read_text(encoding="utf-8")
    assert "6561" in docs
    assert "only" in docs.lower() and "nodeid" in docs.lower()
    assert not DOCS.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6578_strips_airc_suite_folder():
    base = "python -m pytest -q -p no:cacheprovider airc/tests"
    node = "airc/tests/test_x.py::test_y"
    got = bb.append_pytest_nodeid(base, node)
    assert got == (
        "python -m pytest -q -p no:cacheprovider airc/tests/test_x.py::test_y"
    )
    # Must not retain bare suite path as a separate positional
    assert " airc/tests " not in (" " + got + " ")


def test_mrb6578_strips_multiple_suite_paths():
    base = "python -m pytest -q jeeves/tests airc/tests"
    node = "jeeves/tests/test_a.py::test_b"
    got = bb.append_pytest_nodeid(base, node)
    assert "jeeves/tests " not in (got + " ")
    assert "airc/tests" not in got.replace(node, "")
    assert got.endswith(node)


def test_mrb6578_equals_form_option_kept():
    base = "python -m pytest -q -p=no:cacheprovider jeeves/tests"
    node = "jeeves/tests/t.py::test_z"
    got = bb.append_pytest_nodeid(base, node)
    assert "-p=no:cacheprovider" in got
    assert got.endswith(node)
    assert " jeeves/tests " not in (" " + got + " ")


def test_mrb6578_unknown_launcher_legacy_append():
    base = "custom-runner --suite jeeves/tests"
    node = "jeeves/tests/t.py::test_z"
    assert bb.append_pytest_nodeid(base, node) == f"{base} {node}"


def test_mrb6578_empty_nodeid_unchanged():
    base = "python -m pytest -q airc/tests"
    assert bb.append_pytest_nodeid(base, "") == base
    assert bb.append_pytest_nodeid(base, "   ") == base
