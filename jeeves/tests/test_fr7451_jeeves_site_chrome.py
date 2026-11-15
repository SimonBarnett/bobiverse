"""FR #7451: /jeeves appliance pages use shared site.css + site-header/footer."""
from __future__ import annotations

import jeeves_settings_http as http

SITE_CSS = 'href="/site.css"'
SITE_HEADER = 'class="site-header"'
SITE_FOOTER = 'class="site-footer"'
SHELL = 'class="shell"'


def _pages(prefix: str = "/jeeves") -> dict[str, str]:
    return {
        "login": http._render_login_html(prefix=prefix),
        "settings": http._render_html([], prefix=prefix),
        "queue": http._render_queue_html([], [], prefix=prefix),
        "pools": http._render_pools_html({"machines": []}, prefix=prefix),
        "status": http._render_status_html(
            {
                "version": "0",
                "source_commit": "",
                "uptime_s": 0,
                "queue": {"unaccepted": 0, "accepted": 0},
                "seats": {"live_n": 0, "idle_n": 0},
                "fuel": {"active": []},
                "restart_pending": False,
            },
            prefix=prefix,
        ),
    }


def test_fr7451_every_jeeves_page_links_site_css_and_chrome():
    for name, html in _pages("/jeeves").items():
        assert SITE_CSS in html, f"{name} missing shared stylesheet"
        assert SITE_HEADER in html, f"{name} missing site-header"
        assert SITE_FOOTER in html, f"{name} missing site-footer"
        assert SHELL in html, f"{name} missing shell wrapper"
        # One shared stylesheet only --- no forked copy path.
        assert html.count("site.css") == 1, f"{name} should reference site.css once"
        assert "site-fork.css" not in html


def test_fr7451_lan_root_pages_also_use_site_chrome():
    for name, html in _pages("").items():
        assert SITE_CSS in html, f"lan {name} missing /site.css"
        assert SITE_HEADER in html
        assert SITE_FOOTER in html


def test_fr7451_shell_helpers_emit_shared_markup():
    hdr = http._shell_header(current="settings", include_nav=True, prefix="/jeeves")
    assert 'class="site-header"' in hdr
    assert 'class="nav"' in hdr
    assert "/jeeves/queue" in hdr
    foot = http._shell_footer()
    assert 'class="site-footer"' in foot