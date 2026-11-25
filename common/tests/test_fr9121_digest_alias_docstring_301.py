"""FR #9121 / #9864: digest alias is a fast last-good JSON path (not 301 to report)."""
from __future__ import annotations

import json
from pathlib import Path

import bobcallback as bc
import bobreport


def test_fr9121_module_docstring_says_fast_alias_not_same_json_body():
    doc = (bc.__doc__ or "")
    low = doc.lower()
    assert "same json body" not in low, (
        "module docstring must not claim /bob/v1/digest and /digest serve the same JSON body"
    )
    assert "9864" in doc or "last-good" in low or "lightweight" in low
    assert "/bob/v1/report" in doc
    assert "/bob/v1/digest" in doc


def test_fr9121_digest_aliases_return_fast_json(tmp_path: Path):
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
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
        assert code == 200, path
        doc = json.loads(payload.decode("utf-8"))
        assert isinstance(doc.get("machines"), dict)
        assert doc.get("digest_alias") is True
