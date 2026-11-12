"""FR #6751 / FR-03: settings API + HTML show schema defaults (secrets empty)."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def test_fr6751_api_includes_default_for_non_secret(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("BOB_CODERABBIT_WAIT_MIN", raising=False)
    view = js.api_get_settings(home, client_ip="10.0.0.8")
    assert view["ok"] is True
    row = next(r for r in view["settings"] if r["key"] == "BOB_CODERABBIT_WAIT_MIN")
    assert row["default"] == "12"
    assert "default" in row


def test_fr6751_api_secret_default_is_empty(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GH_TOKEN", "ghs_FAKE_SHOULD_NOT_APPEAR")
    view = js.api_get_settings(home, client_ip="10.0.0.8")
    assert view["ok"] is True
    row = next(r for r in view["settings"] if r["key"] == "GH_TOKEN")
    assert row["default"] == ""
    blob = json.dumps(view)
    assert "ghs_FAKE" not in blob
    assert "SHOULD_NOT_APPEAR" not in blob


def test_fr6751_html_shows_default_for_coderabbit_wait_min():
    """Rendered HTML for BOB_CODERABBIT_WAIT_MIN contains the default 12."""
    settings = [
        {
            "key": "BOB_CODERABBIT_WAIT_MIN",
            "type": "float",
            "default": "12",
            "value": "12",
            "source": "default",
            "secret": False,
            "restart": False,
            "description": "Minutes to wait for CodeRabbit.",
        }
    ]
    html = http._render_html(settings)
    assert "BOB_CODERABBIT_WAIT_MIN" in html
    assert ">Default<" in html or ">default<" in html.lower()
    # Default cell must print 12 (class marker keeps it distinct from other columns).
    assert 'class="setting-default"' in html
    assert ">12<" in html or 'data-default="12"' in html


def test_fr6751_html_secret_has_no_default_secret():
    """GH_TOKEN HTML must not show a default secret; API default stays empty."""
    settings = [
        {
            "key": "GH_TOKEN",
            "type": "secret",
            "default": "",
            "value": "set",
            "source": "env",
            "secret": True,
            "restart": True,
            "description": "GitHub token (write-only).",
        }
    ]
    html = http._render_html(settings)
    assert "GH_TOKEN" in html
    assert 'class="setting-default"' in html
    # Empty default cell for secrets (no invented secret text).
    assert 'data-default=""' in html or 'class="setting-default"></td>' in html or 'class="setting-default">—</td>' in html or 'class="setting-default">-</td>' in html
    for bad in ("ghs_", "github_pat_", "password=", "Bearer "):
        assert bad not in html


def test_fr6751_html_shows_both_when_value_differs_from_default(tmp_path):
    """Non-secret with value != default still shows both (editable current + default)."""
    home = tmp_path / "home"
    home.mkdir()
    # Persist a non-default value via the file store.
    js.api_put_setting(
        home,
        client_ip="10.0.0.8",
        key="BOB_CODERABBIT_WAIT_MIN",
        value="30",
        actor="tester",
    )
    view = js.api_get_settings(home, client_ip="10.0.0.8")
    assert view["ok"] is True
    row = next(r for r in view["settings"] if r["key"] == "BOB_CODERABBIT_WAIT_MIN")
    assert row["default"] == "12"
    assert str(row["value"]) == "30"

    html = http._render_html([row])
    assert 'value="30"' in html
    assert 'class="setting-default"' in html
    assert ">12<" in html or 'data-default="12"' in html
    # Default must not overwrite the control when current differs.
    assert 'value="12"' not in html
