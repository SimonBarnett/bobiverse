"""FR #6753 / FR-05: non-empty choices render a select; bools stay checkboxes."""
from __future__ import annotations

from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def test_fr6753_choices_tuple_defaults_empty():
    spec = js._spec("X_FAKE", "str", "")
    assert spec.choices == ()


def test_fr6753_fixture_choices_renders_select_not_text():
    html = http._render_html(
        [
            {
                "key": "DEMO_MODE",
                "type": "str",
                "value": "a",
                "source": "file",
                "secret": False,
                "restart": False,
                "description": "x",
                "choices": ("a", "b"),
            }
        ]
    )
    assert "<select name=\"DEMO_MODE\">" in html
    assert 'type="text"' not in html
    assert 'value="a"' in html
    assert "selected" in html
    assert 'name="DEMO_MODE" type="text"' not in html


def test_fr6753_value_outside_list_is_extra_selected_option():
    html = http.render_setting_input(
        {
            "key": "DEMO_MODE",
            "type": "str",
            "value": "c",
            "choices": ("a", "b"),
        }
    )
    assert "<select name=\"DEMO_MODE\">" in html
    assert 'value="c"' in html
    assert html.count("selected") >= 1
    assert 'option value="c" selected' in html.replace("'", '"') or 'value="c" selected' in html


def test_fr6753_bool_with_choices_still_checkbox():
    html = http.render_setting_input(
        {
            "key": "BOB_FUEL_FLEET",
            "type": "bool",
            "value": "1",
            "choices": ("0", "1"),
        }
    )
    assert 'type="checkbox"' in html
    assert "<select" not in html


def test_fr6753_schema_walk_empty_choices():
    for spec in js.SCHEMA:
        assert spec.choices == (), spec.key


def test_fr6753_docs_mention_select():
    root = Path(__file__).resolve().parents[2]
    text = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "select" in text.lower() or "dropdown" in text.lower()
    assert "FR #6753" in text or "FR-05" in text
