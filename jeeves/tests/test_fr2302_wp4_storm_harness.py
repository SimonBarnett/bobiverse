"""FR #2302: WP4 deterministic two-worker queue storm harness."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_wp4_storm as storm

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
MOD = ROOT / "common/scripts/jeeves_wp4_storm.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path
    assert path.read_bytes().endswith(b"\n"), path


def test_fr2302_storm_module_and_docs():
    _no_bom(MOD)
    _no_bom(DOC)
    text = DOC.read_text(encoding="utf-8")
    assert "2302" in text
    assert "WP4" in text
    assert "jeeves_wp4_storm" in text
    assert "two-worker" in text.lower() or "two workers" in text.lower()
    assert "50" in text
    # living umbrella stays Refs-only from WP PRs
    assert "Refs" in text or "#1993" in text


def test_fr2302_storm_deterministic_accounting(tmp_path):
    a = storm.run_storm(
        tmp_path / "a",
        seed=7,
        pings=20,
        machines=["marchhare", "flamingo"],
        workers_per_machine=2,
    )
    b = storm.run_storm(
        tmp_path / "b",
        seed=7,
        pings=20,
        machines=["marchhare", "flamingo"],
        workers_per_machine=2,
    )
    assert a.ok, a.failures
    assert b.ok, b.failures
    assert a.enqueue_added == 20
    assert sorted(a.done_ids) == sorted(b.done_ids)
    assert len(set(a.done_ids)) == 20
    assert not any(str(x).startswith("error:queue") for x in a.enqueue_errors)
    # Same seed → same enqueue submission schedule (completion order may interleave)
    assert a.enqueue_schedule == b.enqueue_schedule
    assert sorted(a.done_ids) == sorted(a.enqueue_schedule)


def test_fr2302_storm_json_summary(tmp_path):
    out = tmp_path / "storm.json"
    code = storm.main(
        [
            "--home",
            str(tmp_path / "h"),
            "--seed",
            "3",
            "--pings",
            "12",
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
    assert payload["pings"] == 12
    assert payload["done_ok"] == 12 or len(payload["done_ids"]) == 12
    assert payload["inproc_lock"] is True
