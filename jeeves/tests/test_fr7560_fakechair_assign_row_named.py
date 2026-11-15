"""FR #7560: FakeChair binds Client._assign_row_named for !assign tests."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

CHAIR_TEST = REPO / "jeeves" / "tests" / "test_chair_commands_020.py"


def test_fr7560_fakechair_binds_assign_row_named():
    text = CHAIR_TEST.read_text(encoding="utf-8")
    for name in ("_assign_row_named", "_finish_assign_result"):
        assert f'"{name}"' in text or f"'{name}'" in text, name
    assert "def _names_refresh_for_assign" in text
    assert "FR #7560" in text
    # Must not park unit !assign as waiting (no live NAMES).
    assert "return None" in text[text.index("def _names_refresh_for_assign") :]


def test_fr7560_fakechair_instance_has_assign_helpers(tmp_path, monkeypatch):
    import test_chair_commands_020 as t

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    c = t.FakeChair(tmp_path)
    assert callable(getattr(c, "_assign_row_named", None))
    assert callable(getattr(c, "_finish_assign_result", None))
    assert c._names_refresh_for_assign("#marchhare") is None
    assert any(s.startswith("NAMES #marchhare") for s in c.sent)
