"""docs/mrb-6779: every non-secret settings row prints a Default cell."""
from __future__ import annotations

import jeeves_settings as js
import jeeves_settings_http as http


def test_docs_mrb6779_every_non_secret_has_default_cell(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    view = js.api_get_settings(home, client_ip="127.0.0.1")
    assert view.get("ok") is True
    html = http._render_html(list(view.get("settings") or []))
    assert ">Default<" in html
    for row in view["settings"]:
        if row.get("secret"):
            continue
        key = row["key"]
        assert key in html
        assert 'class="setting-default"' in html
        default = str(row.get("default") or "")
        if default:
            assert f'data-default="{default}"' in html or f">{default}<" in html
