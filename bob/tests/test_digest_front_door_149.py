"""FR #149: public digest front-door is /bob/v1/report (IIS); /bob/v1/digest is local bobcallback only."""
from __future__ import annotations

import json

import pytest

import bobcallback
import bobreport
import registered_machines as rm


ALLOW = {"127.0.0.1"}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    return tmp_path


def test_public_digest_path_is_report_only():
    assert bobcallback.PUBLIC_DIGEST_PATH == "/bob/v1/report"
    assert bobcallback.PUBLIC_DIGEST_PATH == bobcallback.REPORT_PATH
    # Local bobcallback still serves the legacy alias paths.
    assert bobcallback.DIGEST_PATH in bobcallback.DIGEST_GET_PATHS
    assert bobcallback.DIGEST_ALIAS in bobcallback.DIGEST_GET_PATHS
    assert bobcallback.REPORT_PATH in bobcallback.DIGEST_GET_PATHS


def test_local_handler_serves_digest_on_report_and_legacy_paths(home):
    for route in ("/bob/v1/report", "/bob/v1/digest", "/digest"):
        code, raw = bobcallback.handle_request(
            "GET", route, {}, b"", "127.0.0.1", home, ALLOW,
        )
        assert code == 200, route
        doc = json.loads(raw.decode("utf-8"))
        assert "machines" in doc


def test_argparse_description_points_public_readers_at_report():
    desc = bobcallback.CLI_DESCRIPTION
    assert "/bob/v1/report" in desc
    assert "front-door GET is /bob/v1/report" in desc
