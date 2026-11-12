"""FR #6752: SCHEMA SettingSpec group / title / description (gap test)."""
from __future__ import annotations

from pathlib import Path

import jeeves_settings as js


def _repo() -> Path:
    return Path(__file__).resolve().parents[2]


def test_fr6752_schema_walk_finds_zero_empty_groups():
    gaps = js.schema_group_gaps()
    assert gaps == [], f"SCHEMA keys missing group fields: {gaps}"


def test_fr6752_later_schema_key_without_group_fails_gap_test(monkeypatch):
    """Any SCHEMA key added later must set the same three fields."""
    fake = js.SettingSpec(
        key="BOB_FAKE_UNGROUPED",
        type="str",
        default="",
        store="file",
        restart=False,
    )
    monkeypatch.setattr(js, "SCHEMA", js.SCHEMA + (fake,))
    gaps = js.schema_group_gaps()
    assert "BOB_FAKE_UNGROUPED" in gaps


def test_fr6752_groups_table_has_eight_rows_matching_schema():
    rows = js.load_appliance_groups_table(_repo())
    assert len(rows) == 8
    assigned = {k: r.id for r in rows for k in r.keys}
    schema_keys = {s.key for s in js.SCHEMA}
    assert assigned.keys() == schema_keys
    for spec in js.SCHEMA:
        row = next(r for r in rows if r.id == spec.group)
        assert spec.group_title == row.title
        assert spec.group_description == row.description
        assert spec.key in row.keys
