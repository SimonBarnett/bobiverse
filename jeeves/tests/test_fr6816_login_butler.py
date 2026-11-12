"""FR #6816: login HTML shows existing jeeves-butler.ico; no new character art."""
from __future__ import annotations

from pathlib import Path

import jeeves_settings_http as http

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def test_fr6816_login_html_includes_existing_butler():
    html = http._render_login_html()
    assert "jeeves/assets/jeeves-butler.ico" in html or "jeeves-butler.ico" in html
    assert 'alt="' in html.lower() or "jeeves the butler" in html.lower()


def test_fr6816_no_new_image_in_jeeves_assets():
    names = {p.name.lower() for p in ASSETS.iterdir() if p.is_file()}
    assert "jeeves-butler.ico" in names
    extras = names - {
        "jeeves-butler.ico",
        "ntsa-gut-logo.png",
        "bob-systray.ico",
        "readme.md",
        ".gitkeep",
    }
    image_extras = {
        n
        for n in extras
        if n.endswith((".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"))
    }
    assert not image_extras, image_extras
