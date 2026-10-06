"""MRB #2710 hostile: grok Plan shares --no-auto-update/--no-alt-screen (FR #2699)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
from repo_layout import resolve


def test_mrb2710_plan_argv_order_prefix_then_permission_mode(tmp_path):
    spec = bw.build_launch(
        "grok",
        "plan",
        r"C:\ai\bob\plan",
        "prompt",
        r"C:\g\agent.exe",
        tmp_path,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert spec.argv[:4] == [
        r"C:\g\agent.exe",
        "--no-auto-update",
        "--no-alt-screen",
        "--cwd",
    ]
    assert spec.argv[4] == r"C:\ai\bob\plan"
    i = spec.argv.index("--permission-mode")
    assert i > 4
    assert spec.argv[i + 1] == "plan"
    assert "--session-id" in spec.argv
    assert "-s" not in spec.argv  # plan uses --session-id, not -s


def test_mrb2710_maintenance_resume_keeps_shared_prefix(tmp_path):
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    spec = bw.build_launch(
        "grok",
        "maintenance",
        r"C:\ai\jeeves",
        "prompt",
        r"C:\g\agent.exe",
        tmp_path,
        resume_session_id=sid,
    )
    assert spec.argv[1:4] == ["--no-auto-update", "--no-alt-screen", "--cwd"]
    assert "--resume" in spec.argv
    assert spec.argv[spec.argv.index("--resume") + 1] == sid


def test_mrb2710_plan_skill_documents_no_auto_update():
    skill = resolve("bob/.grok/skills/bobiverse-bob-plan/SKILL.md").read_text(encoding="utf-8")
    assert "--no-auto-update" in skill
    assert "FR #2699" in skill or "2699" in skill


def test_mrb2710_no_second_permission_mode_plan_argv_outside_build_launch():
    """Grok seat --permission-mode plan must only be assembled in build_launch."""
    root = resolve(".")
    hits = []
    for rel in (
        "bob/scripts/bob_worker.py",
        "bob/tray/tools/Watch-BobTray.ps1",
        "bob/tray/dialogs/BobTray.cs",
        "jeeves/scripts/Start-JeevesMaintenance.ps1",
        "common/scripts/jeeves_maintenance.py",
    ):
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8-sig")
        if "--permission-mode" in text and "plan" in text:
            hits.append(rel)
    assert hits == ["bob/scripts/bob_worker.py"], hits
