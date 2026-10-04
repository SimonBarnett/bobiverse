"""MRB #2292 hostile: harvest #2179 unverified WHOIS / silent-operator playbook."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path


def test_mrb2292_never_restart_bobircd_leave_seats():
    text = TS.read_text(encoding="utf-8")
    _no_bom(TS)
    assert "2179" in text
    assert "unverified" in text.lower()
    assert "WHOIS" in text or "whois" in text.lower()
    assert "BobIrcd" in text
    assert "never" in text.lower()
    assert "ircJeeves" in text
    # Must not teach restarting Ergo/BobIrcd as the heal
    row = [ln for ln in text.splitlines() if "2179" in ln or ("not responding" in ln.lower() and "WHOIS" in ln)]
    assert row, "expected troubleshooting row for silent operator / WHOIS"
    joined = "\n".join(row).lower()
    assert "bobircd" in joined
    assert "leave seats" in joined or "leave worker seats" in text.lower() or "leave seats alone" in text.lower()


def test_mrb2292_harvest_log_keep_both_with_main():
    log = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "2179" in log
    assert "WHOIS" in log or "whois" in log.lower()
    assert "BobIrcd" in log
    # keep-both: parallel main lessons must remain
    assert "2285" in log or "nothing queued" in log.lower()
    assert "<<<<<<<" not in log and ">>>>>>>" not in log
