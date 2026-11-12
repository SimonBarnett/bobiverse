"""FR #6750 / FR-02: bool settings are checkboxes; unchecked save posts 0."""
from __future__ import annotations

import re
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def test_fr6750_every_bool_schema_key_is_a_checkbox():
    settings = [
        {
            "key": spec.key,
            "type": spec.type,
            "value": spec.default,
            "source": "default",
            "secret": spec.secret,
            "restart": spec.restart,
            "description": spec.description,
        }
        for spec in js.SCHEMA
    ]
    html = http._render_html(settings)
    bools = [s for s in js.SCHEMA if s.type == "bool"]
    assert bools, "SCHEMA must include bool keys"
    for spec in bools:
        assert re.search(
            rf'<input[^>]*name="{re.escape(spec.key)}"[^>]*type="checkbox"',
            html,
        ) or re.search(
            rf'<input[^>]*type="checkbox"[^>]*name="{re.escape(spec.key)}"',
            html,
        ), spec.key
    for spec in js.SCHEMA:
        if spec.type in ("str", "int", "float"):
            assert f'name="{spec.key}"' in html
            assert f'name="{spec.key}" type="checkbox"' not in html


def test_fr6750_unchecked_bool_posts_value_0():
    puts = http.collect_save_puts(
        [{"name": "BOB_FUEL_FLEET", "type": "checkbox", "checked": False, "value": "1"}]
    )
    assert puts == [{"key": "BOB_FUEL_FLEET", "body": {"value": "0"}}]


def test_fr6750_checked_bool_posts_value_1():
    puts = http.collect_save_puts(
        [{"name": "BOB_FUEL_FLEET", "type": "checkbox", "checked": True, "value": "1"}]
    )
    assert puts == [{"key": "BOB_FUEL_FLEET", "body": {"value": "1"}}]


def test_fr6750_blank_secret_produces_no_put():
    puts = http.collect_save_puts(
        [
            {
                "name": "GH_TOKEN",
                "type": "password",
                "value": "",
                "secret": True,
            }
        ]
    )
    assert puts == []


def test_fr6750_truthy_bool_renders_checked_value_1():
    html = http._render_html(
        [
            {
                "key": "BOB_FUEL_FLEET",
                "type": "bool",
                "value": "1",
                "source": "file",
                "secret": False,
                "restart": False,
                "description": "x",
            }
        ]
    )
    assert 'type="checkbox"' in html
    assert 'name="BOB_FUEL_FLEET"' in html
    assert 'value="1"' in html
    assert "checked" in html


def test_fr6750_docs_mention_checkboxes():
    root = Path(__file__).resolve().parents[2]
    text = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "checkbox" in text.lower()
    assert "FR #6750" in text or "FR-02" in text
