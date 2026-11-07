"""FR #6144: digest HTTP GET/POST must send Bobiverse User-Agent (avoid WAF 403)."""
from __future__ import annotations

import json
from unittest import mock

from repo_layout import ROOT
import sys

sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))

import bobreport  # noqa: E402


def test_fr6144_digest_http_user_agent_constant():
    assert bobreport.DIGEST_HTTP_USER_AGENT.startswith("Bobiverse-bobreport/")


def test_fr6144_fetch_digest_http_sends_user_agent():
    captured = {}

    class _Resp:
        def read(self):
            return json.dumps({"v": 1, "machines": {}}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items()) if hasattr(req, "header_items") else {}
        # urllib stores headers case-insensitive; also expose via .headers
        captured["ua"] = req.get_header("User-agent") or req.get_header("User-Agent")
        captured["url"] = req.full_url
        return _Resp()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        doc = bobreport.fetch_digest_http("https://example.test/bob/v1/report")
    assert isinstance(doc, dict)
    assert captured.get("ua") == bobreport.DIGEST_HTTP_USER_AGENT


def test_fr6144_post_report_json_sends_user_agent():
    captured = {}

    class _Resp:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["ua"] = req.get_header("User-agent") or req.get_header("User-Agent")
        return _Resp()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        code = bobreport.post_report_json(
            {"op": "merge", "machine": "marchhare", "weekly": 75},
            url="https://example.test/bob/v1/report",
        )
    assert code == 204
    assert captured.get("ua") == bobreport.DIGEST_HTTP_USER_AGENT
