"""MRB #6765 fix: checkbox save + empty current value in select (FR #6753)."""
from __future__ import annotations

import jeeves_settings as js
import jeeves_settings_http as http


def test_mrb6765_save_script_uses_checkbox_checked_state():
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
    assert "el.type === 'checkbox'" in html
    assert "el.checked ? '1' : '0'" in html


def test_mrb6765_empty_current_value_kept_as_selected_option():
    html = http.render_setting_input(
        {
            "key": "DEMO_MODE",
            "type": "str",
            "value": "",
            "choices": ("a", "b"),
        }
    )
    assert "<select name=\"DEMO_MODE\">" in html
    assert 'value="" selected' in html or "value=\"\" selected" in html


def test_mrb6765_api_get_settings_serialises_choices_list(tmp_path, monkeypatch):
    monkeypatch.setattr(
        js,
        "SCHEMA",
        (
            js._spec("DEMO_MODE", "str", "a", choices=("a", "b")),
            js._spec("PLAIN", "str", "x"),
        ),
    )
    home = tmp_path / "h"
    home.mkdir()
    doc = js.api_get_settings(home, client_ip="10.0.0.8")
    assert doc["ok"] is True
    by_key = {r["key"]: r for r in doc["settings"]}
    assert by_key["DEMO_MODE"]["choices"] == ["a", "b"]
    assert by_key["PLAIN"]["choices"] == []
