"""MRB #5456 hostile pins for FR #5266 BUILD v1 single runner."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import run_bobiverse_build as runner
from repo_layout import ROOT


def test_mrb5456_claim_excl_and_programdata_paths():
    assert "ProgramData" in str(bb.default_build_route_marker_dir())
    assert "build-routes" in str(bb.default_build_route_marker_dir())
    assert "build-locks.json" in str(bb.default_machine_build_lock_path())
    skill = (ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-build" / "SKILL.md").read_text(encoding="utf-8")
    assert "FR #5266" in skill
    assert "O_EXCL" in skill
    assert not (ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-build" / "SKILL.md").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )


def test_mrb5456_second_claim_same_id_false(tmp_path: Path):
    d = tmp_path / "routes"
    assert bb.claim_build_route_marker(d, "b-1") is True
    assert bb.claim_build_route_marker(d, "b-1") is False


def test_mrb5456_leftover_src_refuses(tmp_path: Path, monkeypatch):
    work = tmp_path / "build-work" / "1.0.9"
    work.mkdir(parents=True)
    src = work / "src"
    src.mkdir()
    (src / "keep").write_text("x", encoding="utf-8")
    monkeypatch.setattr(runner, "_rmtree", lambda _p: None)
    log: list[str] = []
    try:
        runner.checkout("SimonBarnett/bobiverse", "HEAD", work, log)
        raise AssertionError("must refuse leftover src")
    except RuntimeError as exc:
        assert "leftover" in str(exc).lower()
