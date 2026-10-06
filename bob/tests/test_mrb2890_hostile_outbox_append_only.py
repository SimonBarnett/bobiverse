"""MRB #2890 hostile pins for FR #2876 append-only DONE skills (product PR #2890)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEAT = ROOT / "bob" / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"
JOB_IRC = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"
JOB_FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
JOB_MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
TROUBLE = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"


def test_mrb2890_append_only_rule_contiguous_in_seat_and_job_irc():
    needle = (
        "**Always append the DONE/NACK/GIVEUP line - never check the outbox first.** "
        "The worker drains `outbox.txt` every 0.5 s"
    )
    for path in (SEAT, JOB_IRC):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        text = raw.decode("utf-8")
        assert needle in text, path
        assert "its own short command" in text
        assert "outbox: sent" in text or path == SEAT  # seat points to worker.log in same paragraph
        if path == SEAT:
            assert "Proof of send is `outbox: sent" in text


def test_mrb2890_job_fr_done_is_own_fence():
    text = JOB_FR.read_text(encoding="utf-8")
    assert "never check the outbox first" in text
    # DONE Add-Content fence must not also contain gh pr create
    assert "Add-Content -LiteralPath $outbox -Value \"PRIVMSG #shop :DONE FR" in text
    create_i = text.index("gh pr create")
    done_i = text.index('Add-Content -LiteralPath $outbox -Value "PRIVMSG #shop :DONE FR')
    assert create_i < done_i
    # Between the two fences: closing ``` then opening ```
    between = text[create_i:done_i]
    assert between.count("```") >= 2


def test_mrb2890_troubleshooting_seat_vs_ear_outbox():
    text = TROUBLE.read_text(encoding="utf-8")
    assert "outbox.txt.pos" not in text
    assert "outbox: sent" in text
    assert "FR #2876" in text
    assert "never treat an empty file as proof" in text


def test_mrb2890_job_mrb_done_own_command_before_harvest():
    text = JOB_MRB.read_text(encoding="utf-8")
    assert "DONE (own command)" in text
    assert "never check the outbox first; FR #2876" in text
    i = text.index("DONE (own command)")
    window = text[i : i + 500].lower()
    assert window.index("done (own command)") < window.index("harvest")
