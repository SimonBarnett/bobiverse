"""MRB #2307 hostile: WP4 storm harness must not close living #1993; no Ergo/BobIrcd."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_wp4_storm as storm

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
MOD = ROOT / "common/scripts/jeeves_wp4_storm.py"
MOJIBAKE = ("â€", "Ã¢", "ÔÇ", "A��", "�?")


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path


def test_mrb2307_docs_living_fr_and_wp_table():
    text = DOC.read_text(encoding="utf-8")
    _no_bom(DOC)
    assert "2302" in text and "WP4" in text
    assert "jeeves_wp4_storm" in text
    assert "Refs" in text and "1993" in text
    assert "never `Closes`" in text or "never Closes" in text
    assert "BobIrcd" in text
    # WP3 already landed on main; WP4 harness landed; live cutover still open
    assert "WP3" in text and "landed" in text.lower()
    assert "harness landed" in text.lower() or "jeeves_wp4_storm.py" in text
    for bad in MOJIBAKE:
        assert bad not in text, f"mojibake {bad!r}"
    # fenced command block intact (PR tip had broken fences)
    assert "```text" in text or "```\npython common/scripts/jeeves_wp4_storm" in text
    assert "require_machine" in text


def test_mrb2307_storm_no_ergo_paths():
    src = MOD.read_text(encoding="utf-8")
    _no_bom(MOD)
    assert "BobIrcd" not in src or "does not touch" in src
    assert "ircd.yaml" not in src
    assert "enable_inproc_locks" in src
    assert "FR #2302" in src or "2302" in src


def test_mrb2307_storm_accounting_and_leftover_empty(tmp_path):
    summary = storm.run_storm(
        tmp_path / "s",
        seed=11,
        pings=16,
        machines=["marchhare", "flamingo"],
        workers_per_machine=2,
    )
    assert summary.ok, summary.failures
    assert summary.enqueue_added == 16
    assert len(summary.done_ids) == 16
    assert len(set(summary.done_ids)) == 16
    assert summary.inproc_lock is True
    assert not any("error:queue" in str(x) for x in summary.enqueue_errors)


def test_mrb2307_storm_cli_exit_codes(tmp_path):
    out = tmp_path / "out.json"
    code = storm.main(
        [
            "--home",
            str(tmp_path / "h"),
            "--seed",
            "5",
            "--pings",
            "8",
            "--machines",
            "marchhare",
            "--workers-per-machine",
            "2",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["fr"] == 2302
