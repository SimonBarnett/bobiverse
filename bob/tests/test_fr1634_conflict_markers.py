"""FR #1634: refuse merge / CI when tip still has git conflict markers."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_conflict_markers as ccm

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "check-conflict-markers.yml"
SCRIPT = ROOT / "common" / "scripts" / "check_conflict_markers.py"
MRB_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def test_line_has_conflict_marker_detects_git_markers():
    assert ccm.line_has_conflict_marker("<<<<<<< HEAD\n")
    assert ccm.line_has_conflict_marker("<<<<<<< a5c2dfc (fix)\n")
    assert ccm.line_has_conflict_marker("=======\n")
    assert ccm.line_has_conflict_marker(">>>>>>> branch\n")
    assert ccm.line_has_conflict_marker(">>>>>>> a5c2dfc (fix(mrb-1617): x)\n")


def test_line_has_conflict_marker_ignores_markdown_and_tables():
    assert not ccm.line_has_conflict_marker("| ---- | ---- |\n")
    assert not ccm.line_has_conflict_marker("========\n")  # longer underline
    assert not ccm.line_has_conflict_marker("# Title\n")
    assert not ccm.line_has_conflict_marker("a <<<<<<< not at start\n")
    assert not ccm.line_has_conflict_marker("    code ======= mid\n")


def test_scan_text_reports_line_numbers():
    text = "ok\n<<<<<<< HEAD\nleft\n=======\nright\n>>>>>>> tip\n"
    assert ccm.scan_text(text) == [2, 4, 6]


def test_scan_file_finds_markers(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("x\n<<<<<<< HEAD\ny\n", encoding="utf-8")
    hits = ccm.scan_file(p)
    assert hits and hits[0][0] == 2


def test_main_exits_1_on_dirty_tree(tmp_path):
    dirty = tmp_path / "bad.md"
    dirty.write_text("<<<<<<< HEAD\n", encoding="utf-8")
    clean = tmp_path / "ok.md"
    clean.write_text("# fine\n", encoding="utf-8")
    rc = ccm.main(["--root", str(tmp_path), str(tmp_path)])
    assert rc == 1


def test_main_exits_0_on_clean_tree(tmp_path):
    (tmp_path / "ok.md").write_text("# fine\n| ---- | ---- |\n", encoding="utf-8")
    # eight equals is not a conflict separator (git uses exactly seven)
    (tmp_path / "ok2.md").write_text("========\n", encoding="utf-8")
    assert ccm.main(["--root", str(tmp_path), str(tmp_path)]) == 0


def test_cli_script_runs():
    assert SCRIPT.is_file()
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(ROOT), str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_ci_workflow_exists_and_gates_prs():
    assert WF.is_file(), f"missing {WF}"
    text = WF.read_text(encoding="utf-8")
    assert "pull_request" in text
    assert "check_conflict_markers.py" in text
    assert "windows-latest" in text or "ubuntu-latest" in text


def test_mrb_skill_cast_iron_pre_merge_gate():
    assert MRB_SKILL.is_file()
    text = MRB_SKILL.read_text(encoding="utf-8")
    assert "1634" in text or "conflict marker" in text.lower()
    assert "check_conflict_markers" in text or "<<<<<<<" in text
