"""MRB #2426 hostile: FR DONE PASS/FAIL strip + MRB FAIL <url> keeps url field."""
from __future__ import annotations

from pathlib import Path

import shop_listen
from repo_layout import ROOT

PR = "https://github.com/SimonBarnett/bobiverse/pull/2426"
SHOP = ROOT / "common/scripts/shop_listen.py"


def test_mrb2426_fr_done_strips_fail_and_keeps_url():
    p = shop_listen.parse_shop_job_line(f"DONE FR SimonBarnett/bobiverse#2419 FAIL {PR}")
    assert p is not None and p.task == "FR"
    assert p.url == PR
    assert "FAIL" not in (p.result or "").upper()


def test_mrb2426_fr_done_strips_fail_fix_token():
    p = shop_listen.parse_shop_job_line(
        f"DONE FR SimonBarnett/bobiverse#2419 FAIL fix#12 {PR}"
    )
    assert p is not None
    assert p.url == PR
    assert "FAIL" not in (p.result or "").upper()


def test_mrb2426_fr_done_pass_pr_token():
    p = shop_listen.parse_shop_job_line(
        f"DONE FR SimonBarnett/bobiverse#2419 PASS PR {PR}"
    )
    assert p is not None
    assert p.url == PR
    assert p.result in ("PR", PR)


def test_mrb2426_mrb_fail_url_not_glued_into_result():
    p = shop_listen.parse_shop_job_line(
        f"DONE MRB SimonBarnett/bobiverse#2426 FAIL {PR}"
    )
    assert p is not None and p.task == "MRB"
    assert p.result == "FAIL"
    assert p.url == PR


def test_mrb2426_mrb_fail_fix_token_still_works():
    p = shop_listen.parse_shop_job_line(
        f"DONE MRB SimonBarnett/bobiverse#2426 FAIL fix#99 {PR}"
    )
    assert p is not None
    assert p.result.upper().startswith("FAIL")
    assert p.url == PR


def test_mrb2426_uat_pass_unchanged():
    p = shop_listen.parse_shop_job_line("DONE UAT SimonBarnett/bobiverse#1 PASS")
    assert p is not None and p.task == "UAT" and p.result == "PASS"


def test_mrb2426_encoding_shop_listen():
    raw = SHOP.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
