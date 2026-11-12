"""FR #6752: settings HTML one heading + description per Groups table row."""
from __future__ import annotations

import re
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _repo() -> Path:
    return Path(__file__).resolve().parents[2]


def _html() -> str:
    view = js.api_get_settings(Path("."), client_ip="127.0.0.1")
    assert view.get("ok") is True
    return http._render_html(list(view.get("settings") or []))


def _sections(html: str) -> list[tuple[str, str, str]]:
    """(heading, description, inner html) per <section>."""
    found = re.findall(
        r"<section[^>]*>\s*<h2>(.*?)</h2>\s*<p[^>]*>(.*?)</p>(.*?)</section>",
        html,
        flags=re.S,
    )
    return [(h.strip(), d.strip(), inner) for h, d, inner in found]


def test_fr6752_eight_headings_and_descriptions_in_settings_html():
    rows = js.load_appliance_groups_table(_repo())
    html = _html()
    sections = _sections(html)
    assert len(sections) == 8
    assert [s[0] for s in sections] == [r.title for r in rows]
    assert [s[1] for s in sections] == [r.description for r in rows]


def test_fr6752_keys_from_two_groups_not_same_section():
    html = _html()
    sections = _sections(html)
    review = next(s for s in sections if s[0] == "Fuel and review waits")
    secrets = next(s for s in sections if s[0] == "Secrets")
    assert "BOB_FUEL_CODERABBIT" in review[2]
    assert "GH_TOKEN" not in review[2]
    assert "GH_TOKEN" in secrets[2]
    assert "BOB_FUEL_CODERABBIT" not in secrets[2]
