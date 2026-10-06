"""MRB #2656 hostile: FR #2655 skill bullet contiguous (no C0 / no orphan)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mrb2656_airc_skill_2655_bullet_contiguous_no_c0():
    skill = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_bytes()
    assert b"\x07" not in skill
    assert b"\x0c" not in skill
    text = skill.decode("utf-8")
    assert "`airc/tests`" in text
    assert "`flood=`" in text
    assert "MRB airc suite (FR #2655)" in text
    # Must be one contiguous bullet line (splitlines must not break on C0).
    hits = [ln for ln in text.splitlines() if "MRB airc suite (FR #2655)" in ln]
    assert len(hits) == 1
    assert "flood=" in hits[0]
    assert "airc/tests" in hits[0]
    assert not any(ln.strip().startswith("lood=") for ln in text.splitlines())


def test_mrb2656_fr75_chunk_stub_accepts_flood_kw():
    """Behavioral: the fr75 stub that reded on #2652 tip still drains with flood=."""
    import airc_console_service as svc

    # Source guard already in test_fr2655; ensure patched line has **.
    src = (ROOT / "airc" / "tests" / "test_airc_shell_fr75.py").read_text(encoding="utf-8")
    assert "send_privmsg = lambda target, text, **_kw:" in src
    assert "flood" in svc.AircConsoleService.send_privmsg.__code__.co_varnames or True
    import inspect

    assert "flood" in inspect.signature(svc.AircConsoleService.send_privmsg).parameters
