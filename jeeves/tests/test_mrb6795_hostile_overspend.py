"""MRB #6795 hostile pins for FR #6762 overspend line."""
from __future__ import annotations

import jeeves_settings_http as http


def test_mrb6795_negative_and_falsey_omit_line():
    assert http.format_overspend_line(-0.01) == ""
    assert http.format_overspend_line("0.00") == ""
    assert http.format_overspend_line("nope") == ""


def test_mrb6795_overspend_once_not_per_machine():
    html = http._render_pools_html(1.5)
    assert html.count("overspend") == 1
    assert html.count("£1.50") == 1 or html.count("\u00a31.50") == 1


def test_mrb6795_two_decimals_padding():
    assert http.format_overspend_line(2) == "overspend \u00a32.00"
    assert http.format_overspend_line(0.1) == "overspend \u00a30.10"
