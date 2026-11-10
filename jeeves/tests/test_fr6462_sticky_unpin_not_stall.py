"""FR #6462: require_machine=any (operator/FR #6407 unpin) is not a sticky auto-pin."""
from __future__ import annotations

import stall_detectors as sd


def _row(repo, ident, title, body, require_machine, labels=None):
    return {
        "task": "FR",
        "repo": repo,
        "ident": ident,
        "id": f"#{ident}" if not str(ident).startswith("#") else ident,
        "url": f"https://github.com/{repo}/issues/{str(ident).lstrip('#')}",
        "title": title,
        "body": body,
        "require_machine": require_machine,
        "labels": labels or [],
    }


def test_fr6462_operator_any_unpin_is_not_sticky():
    """Live class: ce-priority#16 after FR #6407 rewrite / !unpin -> stamped any, infer ''."""
    snap = {
        "unaccepted": [
            _row(
                "SimonBarnett/ce-priority",
                "16",
                "Day Works v1.3: finish WP3-WP4 and Gates C-G per dayworks/docs/vision.md",
                "Vision pack for CE Day Works v1.3 on Priority ERP.",
                "any",
            ),
            _row(
                "SimonBarnett/ce-priority",
                "17",
                "dayworks: FR: WP3 ZCLA_ELEDITLOGREM detailed spec",
                "Gate C CASE/DOCNO/steps for UNPARK",
                "any",
            ),
        ]
    }
    assert sd.detect_sticky_auto_pin(snap) == []


def test_fr6462_unpin_tokens_none_star_dash_silent():
    for tok in ("none", "*", "-", "ANY", "None"):
        snap = {
            "unaccepted": [
                _row(
                    "SimonBarnett/a-search",
                    "9999",
                    "plain search bug",
                    "no pin keywords here",
                    tok,
                )
            ]
        }
        assert sd.detect_sticky_auto_pin(snap) == [], tok


def test_fr6462_real_sticky_machine_still_fires():
    snap = {
        "unaccepted": [
            _row(
                "SimonBarnett/a-search",
                "9999",
                "plain search bug",
                "no pin keywords here",
                "redqueen",
            )
        ]
    }
    found = sd.detect_sticky_auto_pin(snap)
    assert len(found) == 1
    assert found[0]["id"] == sd.STICKY_PIN_ID
    assert found[0]["evidence"]["stamped"] == "redqueen"
