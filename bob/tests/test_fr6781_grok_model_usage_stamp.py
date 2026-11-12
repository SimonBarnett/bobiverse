"""FR #6781: worker measure_done_usage stamps Grok modelUsage onto DONE."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import done_usage  # noqa: E402


class _FakeIrc:
    shop = "#redqueen"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def say(self, target: str, text: str) -> bool:
        self.sent.append((target, text))
        return True


def test_measure_done_usage_grok_uses_single_model_usage(tmp_path: Path, monkeypatch):
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(
        json.dumps(
            {
                "session": {
                    "inputTokens": 999,
                    "outputTokens": 99,
                    "cachedReadTokens": 88,
                    "primaryModelId": "other-primary",
                    "modelUsage": {
                        "grok-4.5-build": {
                            "inputTokens": 100,
                            "outputTokens": 20,
                            "cachedReadTokens": 5,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_USAGE_PATH", str(usage_path))

    class _Sup:
        kind = "grok"
        cwd = str(tmp_path)
        sessions = ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]
        sessions_root = tmp_path
        run_dir = tmp_path

        def measure_done_usage(self, *, apply_baseline: bool = True):
            return bw.Supervisor.measure_done_usage(self, apply_baseline=False)

        def enrich_done_line(self, payload: str) -> str:
            return done_usage.enrich_done_payload(payload, self.measure_done_usage())

        def _usage_baseline_path(self):
            return None

    outbox = tmp_path / "outbox.txt"
    outbox.write_text(
        "PRIVMSG #redqueen :DONE FR o/r#6781 https://github.com/o/r/pull/1\n",
        encoding="utf-8",
    )
    irc = _FakeIrc()
    n = bw.drain_outbox(
        outbox,
        irc,
        lambda _m: None,
        enrich_line=_Sup().enrich_done_line,
    )
    assert n == 1
    text = irc.sent[0][1]
    assert "model=xai/grok-4.5-build" in text
    assert "tokens_in=100" in text
    assert "tokens_out=20" in text
    assert "tokens_cached=5" in text
    assert "other-primary" not in text
