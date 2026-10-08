"""docs/mrb-3496: hostile pins for FR #3452 local_only never-flush."""
from __future__ import annotations

from repo_layout import ROOT, resolve

CRASH = ROOT / "common/scripts/crash_report.py"
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
AIRC = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
PRODUCT = ROOT / "common/tests/test_fr3452_local_only_spool_never_flush.py"
HOOK = resolve("third_party/bob-tray/dialogs/CrashHook.cs")


def test_mrb3496_flush_spool_drops_local_only_before_post():
    t = CRASH.read_text(encoding="utf-8")
    assert "FR #3452" in t
    flush = t.split("def flush_spool", 1)[1]
    assert "local_only" in flush
    assert 'err_raw in {' in flush or 'err_raw in {"' in flush or "err_raw in {" in flush
    assert "local_only" in flush and "local-only" in flush
    # Real offline still posts (error=post_failed path remains).
    assert "post_failed" in t or "filer_post" in flush


def test_mrb3496_csharp_flush_and_writespool_stamp():
    text = HOOK.read_text(encoding="utf-8-sig")
    assert "FR #3452" in text
    flush = text.split("public static void FlushSpool", 1)[1]
    assert "local_only" in flush
    write = text.split("static void WriteSpool", 1)[1]
    assert 'payload["local_only"] = true' in write or 'local_only"] = true' in write


def test_mrb3496_skills_and_product_tests():
    fleet = FLEET.read_text(encoding="utf-8")
    assert "FR #3452" in fleet
    assert "local_only" in fleet
    airc = AIRC.read_text(encoding="utf-8")
    assert "Crash-report opt-out (FR #3291)" in airc
    assert "FR #3452" in airc
    assert PRODUCT.is_file()
    p = PRODUCT.read_text(encoding="utf-8")
    assert "test_fr3452_flush_drops_local_only_flag_when_send_true" in p
    assert "test_fr3452_opt_out_then_reenable_never_posts_local_only" in p
    assert "test_fr3452_flush_still_sends_real_offline_spool" in p
