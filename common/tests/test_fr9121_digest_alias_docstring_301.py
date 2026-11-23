"""FR #9121: bobcallback digest-alias docs match 301 redirect behaviour."""
from __future__ import annotations

from pathlib import Path

import bobcallback as bc


def test_fr9121_module_docstring_says_301_not_same_json_body():
    doc = (bc.__doc__ or "")
    low = doc.lower()
    assert "same json body" not in low, (
        "module docstring must not claim /bob/v1/digest and /digest serve the same JSON body"
    )
    assert "301" in doc
    assert "/bob/v1/report" in doc
    assert "/bob/v1/digest" in doc


def test_fr9121_digest_aliases_301_to_report(tmp_path: Path):
    for path in (bc.DIGEST_PATH, bc.DIGEST_ALIAS):
        bc.stash_response_headers([])
        code, payload = bc.handle_request(
            "GET",
            path,
            {},
            b"",
            "127.0.0.1",
            tmp_path,
            allow_ips={"127.0.0.1"},
        )
        assert code == 301, path
        assert payload == b""
        headers = dict(bc.pop_response_headers())
        assert headers.get("Location") == bc.REPORT_PATH, path
