"""MRB #6806: LAN gate, stale hides zero percent, login page not JSON."""
from __future__ import annotations

import jeeves_settings as js
import jeeves_settings_http as http


def test_mrb6806_non_lan_api_get_pools_forbidden(tmp_path):
    view = js.api_get_pools(tmp_path, client_ip="8.8.8.8")
    assert view.get("ok") is False
    assert "forbidden" in str(view.get("error") or "").lower()


def test_mrb6806_stale_zero_does_not_say_out_of_tokens():
    html = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {
                    "id": "walrus",
                    "remaining_pct": 0,
                    "fuel_stale": True,
                    "reset_label": None,
                }
            ],
        }
    )
    assert "[stale]" in html
    assert "0%" not in html
    assert "out of tokens" not in html.lower()
