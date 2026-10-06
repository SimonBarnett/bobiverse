"""FR #2876: always append DONE/NACK/GIVEUP; never guard on drained outbox."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAT = (
    ROOT
    / "agents"
    / "worker"
    / ".grok"
    / "skills"
    / "bobiverse-worker-seat"
    / "SKILL.md"
)
JOB_IRC = ROOT / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"
JOB_FR = ROOT / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
JOB_MRB = ROOT / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
TROUBLE = ROOT / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"

SKILL_ROOTS = [
    ROOT / ".grok" / "skills",
    ROOT / "agents" / "worker" / ".grok" / "skills",
    ROOT.parents[0] / "common" / ".grok" / "skills",
]

GUARD_RES = [
    re.compile(r"(?i)-notmatch\s+['\"]DONE"),
    re.compile(r"(?i)Get-Content[^\n]{0,60}outbox"),
    re.compile(r"(?i)Test-Path[^\n]{0,60}outbox"),
    re.compile(r"DONE already present"),
]


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
    text = raw.decode("utf-8")
    assert text.endswith("\n"), f"missing trailing newline: {path}"
    # Real conflict markers are line-leading; skills document the marker glyphs in prose.
    assert not re.search(r"(?m)^<<<<<<<", text), f"conflict markers in {path}"
    assert not re.search(r"(?m)^>>>>>>>", text), f"conflict markers in {path}"
    return text


def test_worker_seat_and_job_irc_pin_append_only_rule():
    for path in (SEAT, JOB_IRC):
        text = _read(path)
        assert "never check the outbox first" in text, path
        assert "every 0.5 s" in text, path
        assert "its own short command" in text, path


def test_job_irc_rule_covers_nack_and_giveup():
    text = _read(JOB_IRC)
    # Contiguous DONE/NACK/GIVEUP naming in the append-only rule.
    assert "DONE/NACK/GIVEUP" in text
    idx = text.index("never check the outbox first")
    window = text[max(0, idx - 120) : idx + 400]
    assert "DONE/NACK/GIVEUP" in window


def test_no_skill_teaches_outbox_guard():
    hits: list[str] = []
    for root in SKILL_ROOTS:
        if not root.is_dir():
            continue
        for skill in root.rglob("SKILL.md"):
            text = skill.read_text(encoding="utf-8")
            for rx in GUARD_RES:
                if rx.search(text):
                    hits.append(f"{skill.relative_to(ROOT.parents[0])}: {rx.pattern}")
    assert hits == [], "skills teach outbox guard:\n" + "\n".join(hits)


def test_done_append_snippets_are_standalone():
    fence_re = re.compile(r"```(?:powershell)?\n(.*?)```", re.DOTALL | re.IGNORECASE)
    bad_tokens = (
        "gh pr merge",
        "gh pr create",
        "Invoke-BobiverseHarvest",
        "worktree remove",
    )
    offenders: list[str] = []
    for path in (SEAT, JOB_IRC, JOB_FR, JOB_MRB):
        text = _read(path)
        for block in fence_re.findall(text):
            if "Add-Content" not in block:
                continue
            if not re.search(r":DONE |NACK |GIVEUP ", block):
                continue
            nonblank = [ln for ln in block.splitlines() if ln.strip()]
            if len(nonblank) > 3:
                offenders.append(f"{path.name}: >3 non-blank lines in DONE Add-Content fence")
            for tok in bad_tokens:
                if tok in block:
                    offenders.append(f"{path.name}: DONE Add-Content fence contains {tok}")
    assert offenders == [], "\n".join(offenders)


def test_troubleshooting_has_no_seat_outbox_pos():
    text = _read(TROUBLE)
    assert "outbox.txt.pos" not in text
    assert "outbox: sent" in text


def test_job_mrb_orders_done_before_harvest():
    text = _read(JOB_MRB)
    assert "DONE (own command)" in text
    done_i = text.index("DONE (own command)")
    # After the DONE (own command) pin, harvest must appear in the same step window.
    window = text[done_i : done_i + 400]
    assert "harvest" in window.lower()
    assert window.lower().index("done (own command)") < window.lower().index("harvest")
