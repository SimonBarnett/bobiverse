"""FR #5394: CodeRabbit lookup shares the !bored GitHub call budget."""
from __future__ import annotations

from pathlib import Path

import fuel_chain
import gitclaim


def test_fr5394_stamped_ready_skips_lookup(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    calls = []
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_reviewed",
        lambda *a, **k: calls.append(1) or True,
    )
    row = {
        "task": "MRB",
        "repo": "o/r",
        "id": "#1",
        "coderabbit": "ready",
        "coderabbit_wait_since": 1.0,
    }
    assert fuel_chain.apply_mrb_coderabbit_gate(row, 2.0) is False
    assert calls == []
    assert row["coderabbit"] == "ready"


def test_fr5394_injected_lookup_used_not_live(monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    live = []
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_reviewed",
        lambda *a, **k: live.append(1) or True,
    )
    seen = []

    def lookup(repo, num):
        seen.append((repo, num))
        return False

    row = {"task": "MRB", "repo": "o/r", "id": "#9", "coderabbit_wait_since": 1.0}
    hold = fuel_chain.apply_mrb_coderabbit_gate(row, 2.0, lookup=lookup)
    assert hold is True
    assert seen == [("o/r", "9")]
    assert live == []


def test_fr5394_offer_budget_exhausted_does_not_add_http(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "15")
    live = []
    monkeypatch.setattr(
        fuel_chain,
        "lookup_coderabbit_reviewed",
        lambda *a, **k: live.append(1) or False,
    )
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/r",
                    "task": "MRB",
                    "id": "#2",
                    "url": "https://github.com/o/r/pull/2",
                    "title": "pr",
                    "line": "MRB #2",
                    "seq": 2,
                    "state": "open",
                    "coderabbit_wait_since": 1_000.0,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(
        home, "n-1", "#n", now=1_000.0 + 60.0, pr_exists=lambda r, n: True
    )
    assert st == "empty" and job is None
    # pr_exists consumes the one-call budget; coderabbit must not fire a second GET.
    assert live == []


def test_fr5394_pins():
    here = Path(__file__).resolve()
    gc = (here.parents[1] / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    fc = (here.parents[1] / "scripts" / "fuel_chain.py").read_text(encoding="utf-8")
    assert '"coderabbit"' in gc
    assert "lookup=cr_check" in gc
    assert "FR #5394" in fc
    assert not (here.parents[1] / "scripts" / "fuel_chain.py").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )
