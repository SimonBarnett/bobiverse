"""MRB #2317 hostile: harvest #2309/#2314 nothing-queued / ledger giveup playbook."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
TS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path


def test_mrb2317_monitor_nothing_queued_gates():
    text = MON.read_text(encoding="utf-8")
    _no_bom(MON)
    assert "2309" in text
    assert "offer_focus_top" in text
    assert "seat-ledger" in text or "seat-ledger.json" in text
    assert "review_blocked" in text
    assert "self-MRB" in text or "self-mrb" in text.lower()
    # clear both row + ledger; do not re-clear after ACK+GIVEUP
    assert "giveup" in text.lower()
    assert "ACK" in text and "GIVEUP" in text
    assert "re-clear" in text.lower() or "Do not** re-clear" in text or "do **not** re-clear" in text.lower()
    assert "OFFER_TIMEOUT" in text or "offered_to" in text


def test_mrb2317_troubleshooting_rows():
    text = TS.read_text(encoding="utf-8")
    _no_bom(TS)
    assert "2309" in text or "2314" in text
    assert "seat-ledger" in text or "seat-ledger.json" in text
    assert "offer_focus_top" in text
    rows = [
        ln
        for ln in text.splitlines()
        if "nothing queued" in ln.lower() or "giveup_seats" in ln or "sticky MRB" in ln.lower()
    ]
    assert rows, "expected troubleshooting rows for nothing-queued / ledger / sticky MRB"
    joined = "\n".join(rows).lower()
    assert "ledger" in joined or "seat-ledger" in text.lower()


def test_mrb2317_harvest_log_entry():
    log = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "2309" in log
    assert "2314" in log
    assert "seat-ledger" in log or "ledger" in log.lower()
    assert "offer_focus_top" in log
    assert "<<<<<<<" not in log and ">>>>>>>" not in log
    # keep-both: prior nothing-queued lessons remain
    assert "2243" in log or "2285" in log
