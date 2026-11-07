"""Hostile pin: OpenCode seat gaps docs park (MRB #6161 / docs/mrb-6161)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PARK = ROOT / "bob" / "docs"
VISION = PARK / "vision-opencode-seat-gaps-2026-11-07.md"
GAP = PARK / "gap-opencode-seat-2026-11-07.md"
FR = PARK / "feature-request-opencode-seat-gaps-2026-11-07.md"
MIRRORS = PARK / "fr" / "opencode-seat-gaps"
TSV = MIRRORS / "SMALL-FRS.tsv"


def _park_files() -> list[Path]:
    files = [VISION, GAP, FR]
    files.extend(MIRRORS.rglob("*"))
    return [p for p in files if p.is_file()]


def test_mrb6161_vision_park_locked_success_rows() -> None:
    text = VISION.read_text(encoding="utf-8")
    assert "LOCKED" in text
    for sid in ("S1", "S2", "S3", "S4", "S5"):
        assert f"| {sid} " in text or f"| {sid}|" in text
    assert "Do not re-implement #6120/#6121/#6134" in text
    assert "kind=opencode" in text and "FR #6134" in text
    assert "bob.ntsa.uk/report" in text or "bob.ntsa.uk" in text


def test_mrb6161_small_frs_tsv_maps_oc_ids() -> None:
    rows = TSV.read_text(encoding="utf-8").strip().splitlines()
    assert rows[0].startswith("id\ttitle")
    mapping = {}
    for line in rows[1:]:
        if not line.strip() or line.startswith("#"):
            # related digest paint rows use #6146 style id
            parts = line.split("\t")
            if len(parts) >= 5 and parts[-1].startswith("SimonBarnett/bobiverse#"):
                mapping[parts[0]] = parts[-1]
            continue
        parts = line.split("\t")
        mapping[parts[0]] = parts[-1]
    assert mapping["FR-OC-SYNC"].endswith("#6154")
    assert mapping["FR-OC-WATCHDOG"].endswith("#6156")
    assert mapping["FR-OC-TURN"].endswith("#6157")
    assert mapping["FR-OC-INJECT"].endswith("#6158")
    assert mapping["FR-OC-PACK"].endswith("#6159")
    assert mapping["FR-OC-FLEET"].endswith("#6160")


def test_mrb6161_park_docs_ascii_no_bom_no_closes() -> None:
    for path in _park_files():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        text = raw.decode("utf-8")
        non = [c for c in text if ord(c) > 127]
        assert not non, f"{path} non-ascii {[hex(ord(c)) for c in non[:5]]}"
        for line in text.splitlines():
            assert not line.strip().startswith("Closes "), path


def test_mrb6161_watchdog_and_inject_acceptance_pins() -> None:
    wd = (MIRRORS / "FR-OC-WATCHDOG.md").read_text(encoding="utf-8")
    assert "heartbeat" in wd.lower() or "progress marker" in wd.lower()
    assert "record-pause" in wd
    assert "without limit evidence" in wd or "solely for silence" in wd
    inj = (MIRRORS / "FR-OC-INJECT.md").read_text(encoding="utf-8")
    assert "Enter-only" in inj
    assert "duplicate" in inj.lower()
    turn = (MIRRORS / "FR-OC-TURN.md").read_text(encoding="utf-8")
    assert "turn_started" in turn and "turn_ended" in turn
